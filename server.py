import argparse
import asyncio
import json
import logging
import os
import ssl
import cProfile
import pstats
import io
import av
import uuid

import torch
from aiohttp import web
from aiohttp.web_runner import GracefulExit
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceServer, RTCConfiguration, RTCDataChannel
from aiortc.contrib.media import MediaRelay

from config.app_config import AppConfig
from config.app import App
from middleware.auth import Auth
from services.connection_manager import ConnectionManager
from services.telemetry_service import TelemetryService
from video.detection_service import DetectionService
from video.transformers.unet_transformer import UnetTransformer
from video.transformers.yolo_transformer import YoloTransformer
from video.video_transform_track import VideoTransformTrack
from memory_profiler import profile, memory_usage

logger = logging.getLogger("pc")

profiler = None
args = None


def init_detection_module():
    detection_service = DetectionService()
    detection_service.load_yolo(os.path.join(AppConfig.root_path, "models", AppConfig.damage_detection_model_file))
    detection_service.load_unet_detector(os.path.join(AppConfig.root_path, "models"))
    App.detection_service = detection_service


async def css(request):
    content = open(os.path.join(AppConfig.root_path, "html-files/style.css"), "r").read()
    return web.Response(content_type="text/css", text=content)


async def javascript(request):
    content = open(os.path.join(AppConfig.root_path, "html-files/client-new.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)


async def tailwind(request):
    content = open(os.path.join(AppConfig.root_path, "html-files/tailwind-ui.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def offer_producer(request):
    if App.connection_manager.is_producer_connection_limit_reached():
        logger.error(f"Already receiving {ConnectionManager.MAX_PRODUCER_CONNECTIONS} producing video streams")
        return

    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    peer_connection = App.connection_manager.create_peer_connection(connection_type="producer")

    @peer_connection.on("datachannel")
    def on_datachannel(channel: RTCDataChannel):
        @channel.on("message")
        def on_message(message):
            if isinstance(message, str):
                message_json = json.loads(message)
                if message_json["type"] == "rtt-client":
                    channel.send(message)
                if message_json["type"] == "rtt-client-result":
                    App.telemetry_service.rtt_camera = message_json["rtt"]

    @peer_connection.on("track")
    def on_track(track):
        logging.info("Track %s received", track.kind)

        if track.kind == "video":
            video_subscription = App.connection_manager.media_relay.subscribe(track)
            video_subscription_edge = VideoTransformTrack(App.connection_manager.media_relay.subscribe(track),
                                                          name='cam-edge',
                                                          video_transformer=YoloTransformer(App.detection_service))

            # video_subscription_edge = VideoTransformTrack(App.connection_manager.media_relay.subscribe(track),
            #                                               name='cam-edge',
            #                                               video_transformer=UnetTransformer(App.detection_service,
            #                                                                                 confidence_threshold=0.51))

            peer_connection.subscriptions.append(video_subscription)
            peer_connection.subscriptions.append(video_subscription_edge)
            peer_connection.addTrack(video_subscription_edge)

        @track.on("ended")
        async def on_ended():
            logging.info("Track %s ended", track.kind)
            # await recorder.stop()

    # handle offer
    await peer_connection.setRemoteDescription(offer)
    return await App.connection_manager.create_sdp_response_for_peer_connection(peer_connection)


async def offer_consumer(request):
    logging.info(f"Current memory usage {memory_usage()[0]} MB")
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    consumer_peer_connection = App.connection_manager.create_peer_connection(connection_type="consumer")

    producer_peer_connection = App.connection_manager.get_primary_producer_connection()
    track1 = App.connection_manager.media_relay.subscribe(producer_peer_connection.subscriptions[0], buffered=False)
    track2 = App.connection_manager.media_relay.subscribe(producer_peer_connection.subscriptions[1], buffered=False)

    consumer_peer_connection.addTrack(track1)
    consumer_peer_connection.addTrack(track2)

    # handle offer

    await consumer_peer_connection.setRemoteDescription(offer)
    return await App.connection_manager.create_sdp_response_for_peer_connection(consumer_peer_connection)


async def on_shutdown(app):
    App.telemetry_service.shutdown()
    await App.connection_manager.shutdown()
    profiler.disable()
    s = io.StringIO()
    sortby = 'cumulative'
    ps = pstats.Stats(profiler, stream=s).sort_stats(sortby)
    ps.print_stats()
    print(s.getvalue())
    with open("mprof.out", 'w') as f:
        f.write(s.getvalue())
    loop = asyncio.get_event_loop()
    pending = asyncio.all_tasks(loop=loop)
    for task in pending:
        task.cancel()
        try:
            # Await the task to handle the cancellation properly
            logging.info(f"Awating {task.get_name()}")
            await task
            logging.info(f"{task.get_name()}: {task.done()}")
        except asyncio.CancelledError:
            logging.info(f"Task [{task.get_name()}] cancellation handled")

    pending = asyncio.all_tasks(loop=loop)
    for task in pending:
        await task


def init_app_services():
    App.connection_manager = ConnectionManager()
    App.telemetry_service = TelemetryService(App.connection_manager)
    App.auth_service = Auth(os.path.join(AppConfig.root_path, "auth.json"))


def init_web_app():
    if torch.cuda.is_available():
        logging.info("CUDA is available 🚀🚀🚀")
    else:
        logging.info("CUDA is not available 🐌🐌🐌")

    loop = asyncio.get_event_loop()
    loop.set_debug(True)

    app = web.Application()
    app.middlewares.append(App.auth_service.basic_auth_middleware)

    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", tailwind)
    app.router.add_get("/client-new.js", javascript)
    app.router.add_get("/style.css", css)
    app.router.add_post("/offer", offer_producer)
    app.router.add_post("/viewonly", offer_consumer)

    return app


async def on_startup(app):
    asyncio.create_task(App.telemetry_service.start())
    logging.info("")


def check_if_user_mode():
    if args.create_user:
        logging.info(f"Creating user {args.username} ...")
        if not args.username:
            logging.error("Provide username (--username)!")
            exit(-1)
        if not args.password:
            logging.error("Provide password (--password)!")
            exit(-1)
        App.auth_service.create_user(args.username, args.password)
        exit(0)

    if args.delete_user:
        logging.info(f"Deleting user {args.username} ...")
        if not args.username:
            logging.error("Provide username (--username)!")
            exit(-1)
        App.auth_service.delete_user(args.username)
        exit(0)

    if args.update_user:
        logging.info(f"Updating user {args.username} ...")
        if not args.username:
            logging.error("Provide username (--username)!")
            exit(-1)
        if not args.password:
            logging.error("Provide password (--password)!")
            exit(-1)
        App.auth_service.update_user(args.username, args.password)
        exit(0)


# @profile
def main():
    global profiler
    profiler = cProfile.Profile()
    profiler.enable()
    # logging.basicConfig(level=logging.DEBUG)
    logging.basicConfig(
        format='%(asctime)s.%(msecs)03d | %(name)s | %(levelname)-8s %(message)s',
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S')

    av.logging.set_level(av.logging.CRITICAL)
    logging.getLogger("aioice.ice").setLevel(logging.ERROR)

    AppConfig.root_path = os.path.dirname(os.path.abspath(__file__))
    logging.info(f"{os.path.dirname(os.path.abspath(__file__))}")

    parser = argparse.ArgumentParser(
        description="WebRTC audio / video / data-channels demo"
    )
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port for HTTP server (default: 8080)"
    )
    parser.add_argument("--record-to", help="Write received media to a file.")
    parser.add_argument("--verbose", "-v", action="count")
    parser.add_argument("--damage-model-file", help="Model file to use for airplane damage detection", type=str)

    parser.add_argument("--create-user", help="Create user", action='store_true')
    parser.add_argument("--delete-user", help="Delete user", action='store_true')
    parser.add_argument("--update-user", help="Update user password", action='store_true')
    parser.add_argument("--username", help="Username", type=str)
    parser.add_argument("--password", help="password", type=str)

    global args
    args = parser.parse_args()

    init_app_services()
    check_if_user_mode()

    AppConfig.damage_detection_model_file = args.damage_model_file
    init_detection_module()
    app = init_web_app()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.cert_file:
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        ssl_context.load_cert_chain(args.cert_file, args.key_file)
    else:
        ssl_context = None

    app.on_startup.append(on_startup)

    web.run_app(
        app, access_log=None, host=args.host, port=args.port, ssl_context=ssl_context
    )


if __name__ == "__main__":
    main()

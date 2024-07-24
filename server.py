import argparse
import asyncio
import json
import logging
import os
import ssl
import uuid

import torch
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceServer, RTCConfiguration
from aiortc.contrib.media import MediaRelay

from config.app_config import AppConfig
from config.app import App
from services.message import Message
from services.message_service import MessageService
from services.telemetry_service import TelemetryService
from video.detection_service import DetectionService
from video.video_transform_track import VideoTransformTrack

logger = logging.getLogger("pc")
pcs = set()
relay = MediaRelay()
playerTestVideo = None

video_subscription = None
video_subscription_edge = None

currentFrame = None


def init_detection_module():
    detection_service = DetectionService()
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


async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    configuration = RTCConfiguration(
        iceServers=[RTCIceServer(urls="stun:stun.l.google.com:19302")]
    )

    pc = RTCPeerConnection(configuration=configuration)
    pc_id = "connection-%s" % uuid.uuid4()
    pcs.add(pc)

    def log_info(msg, *args):
        logger.info(pc_id + " " + msg, *args)

    log_info("Created for %s", request.remote)

    @pc.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            if isinstance(message, str):
                message_json = json.loads(message)
                if message_json["type"] == "rtt-client":
                    channel.send(message)
                if message_json["type"] == "rtt-client-result":
                    App.telemetry_service.rtt_camera = message_json["rtt"]

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        log_info("Connection state is %s", pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        log_info("Track %s received", track.kind)

        if track.kind == "video":
            global video_subscription, video_subscription_edge
            video_subscription = relay.subscribe(track)
            video_subscription_edge = VideoTransformTrack(relay.subscribe(track), transform='airplane-damage',
                                                          name='cam-edge',
                                                          detection_service=App.detection_service)
            pc.addTrack(video_subscription_edge)

        @track.on("ended")
        async def on_ended():
            log_info("Track %s ended", track.kind)
            # await recorder.stop()

    # handle offer
    await pc.setRemoteDescription(offer)
    # await recorder.start()

    # send answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )


async def viewer(request):
    global video_subscription, video_subscription_edge, playerTestVideo
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    configuration = RTCConfiguration(
        iceServers=[RTCIceServer(urls="stun:stun.l.google.com:19302")]
    )

    pc = RTCPeerConnection(configuration=configuration)

    pc_id = "PeerConnection(%s)" % uuid.uuid4()
    pcs.add(pc)

    def log_info(msg, *args):
        logger.info(pc_id + " " + msg, *args)

    log_info("Created for %s", request.remote)

    @pc.on("datachannel")
    def on_datachannel(channel):
        App.message_service.channel = channel

        @channel.on("message")
        def on_message(message_json):
            message = Message.from_json(message_json)
            if message.payload["type"] == "rtt":
                # Just return message
                App.message_service.send_message(message)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        log_info("Connection state is %s", pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    track1 = relay.subscribe(video_subscription)
    stream1 = pc.addTrack(track1)

    track2 = relay.subscribe(video_subscription_edge)
    stream2 = pc.addTrack(track2)

    # handle offer
    await pc.setRemoteDescription(offer)

    # send answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )


async def on_shutdown(app):
    App.telemetry_service.shutdown()
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


def init_app():
    loop = asyncio.get_event_loop()
    loop.set_debug(True)

    app = web.Application()

    init_detection_module()
    App.message_service = MessageService()
    App.telemetry_service = TelemetryService(App.message_service)

    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/" + args.url_key, tailwind)
    app.router.add_get("/client-new.js", javascript)
    app.router.add_get("/style.css", css)
    app.router.add_post("/offer" + args.url_key, offer)
    app.router.add_post("/viewonly", viewer)

    return app


async def on_startup(app):
    asyncio.create_task(App.telemetry_service.start())


if __name__ == "__main__":
    # logging.basicConfig(level=logging.DEBUG)
    logging.basicConfig(
        format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S')

    AppConfig.root_path = os.path.dirname(os.path.abspath(__file__))
    logging.info(f"{os.path.dirname(os.path.abspath(__file__))}")

    if torch.cuda.is_available():
        logging.info("CUDA is available 🚀🚀🚀")
    else:
        logging.info("CUDA is not available 🐌🐌🐌")

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
    parser.add_argument("--url-key", help="String for URL disguise", default="", type=str)
    parser.add_argument("--damage-model-file", help="Model file to use for airplane damage detection", type=str)
    args = parser.parse_args()

    AppConfig.damage_detection_model_file = args.damage_model_file

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.cert_file:
        ssl_context = ssl.SSLContext()
        ssl_context.load_cert_chain(args.cert_file, args.key_file)
    else:
        ssl_context = None

    app = init_app()
    app.on_startup.append(on_startup)

    web.run_app(
        app, access_log=None, host=args.host, port=args.port, ssl_context=ssl_context
    )

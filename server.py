import argparse
import asyncio
import base64
import json
import logging
import os
import ssl
import time
from pathlib import Path

import aiohttp_jinja2
import av
import cv2
import jinja2
import numpy as np

import torch
from aiohttp import web
from aiortc import RTCSessionDescription, RTCDataChannel
from aiortc.contrib.media import MediaBlackhole, MediaRecorder

from config.app_config import AppConfig
from config.app import App
from middleware.auth import Auth
from services.connection_manager import ConnectionManager
from services.telemetry_service import TelemetryService
from video.detection_service import DetectionService
from video.transformers.yolo_transformer import YoloTransformer
from video.video_transform_track import VideoTransformTrack

from video.video_transform_track_debug import VideoTransformTrackDebug

logger = logging.getLogger("pc")

profiler = None
args = None

MAX_WIDTH = 1600
MAX_HEIGHT = 1600


def rescale_image(image, max_width, max_height):
    height, width = image.shape[:2]
    if width > max_width or height > max_height:
        # Calculate the scaling factor while maintaining the aspect ratio
        scaling_factor = min(max_width / width, max_height / height)
        new_width = int(width * scaling_factor)
        new_height = int(height * scaling_factor)
        resized_image = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)
        return resized_image
    return image


def init_detection_module():
    detection_service = DetectionService()
    detection_service.load_models()
    # detection_service.load_yolo(os.path.join(AppConfig.root_path, "models", AppConfig.damage_detection_model_file))
    # detection_service.load_unet_detector(os.path.join(AppConfig.root_path, "models"))
    App.detection_service = detection_service


async def css(request):
    content = open(os.path.join(AppConfig.root_path, "html-files/style.css"), "r").read()
    return web.Response(content_type="text/css", text=content)


async def javascript(request):
    content = open(os.path.join(AppConfig.root_path, "html-files/app.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)


@aiohttp_jinja2.template('pages/video-detection.html')
async def tailwind(request):
    return {}


@aiohttp_jinja2.template('pages/image-analyzer.html')
async def image_analyzer_html(request):
    return {}


@aiohttp_jinja2.template('pages/image-detection.html')
async def image_detection_html(request):
    return {}


async def image_analyzer_upload_endpoint(request):
    contentBytes = await request.content.read()
    contentJson = json.loads(contentBytes.decode())

    image_base64 = contentJson['image']

    model_id = "fence-detection-unet"
    if 'modelId' in contentJson:
        model_id = contentJson['modelId']

    # Convert the image data to a numpy array
    np_data = np.frombuffer(base64.b64decode(image_base64), np.uint8)

    images_records_dir = os.path.join(AppConfig.records_directory(), "images")
    Path.mkdir(Path(images_records_dir), exist_ok=True, parents=True)

    # Decode the numpy array to an OpenCV image
    img = cv2.imdecode(np_data, cv2.IMREAD_COLOR)

    timestamp = time.strftime('%Y%m%d-%H_%M_%S')

    cv2.imwrite(os.path.join(images_records_dir, timestamp + "-original.jpg"), img)
    model = App.detection_service.get_model_by_id(model_id)
    processed_img = await model.detect_yolo_as_image(img, font_scale=4, thickness=10)

    processed_img = rescale_image(processed_img, MAX_WIDTH, MAX_HEIGHT)
    cv2.imwrite(os.path.join(images_records_dir, timestamp + "-processed.jpg"), processed_img)

    _, encoded_img = cv2.imencode('.jpg', processed_img)

    # Convert the encoded image to base64
    base64_img = base64.b64encode(encoded_img).decode('utf-8')

    # Create a JSON response with the base64 image
    return web.json_response({'image': base64_img, 'success': 'ok'})


async def models_api_endpoint(request):
    models = App.detection_service.models
    models_json = [{'id': model.model_id, 'name': model.model_name} for model in models]
    return web.json_response(models_json)


async def photos_api_endpoint(request):
    image_dir = os.path.join(AppConfig.root_path, "records/images")
    files = [f for f in os.listdir(image_dir) if os.path.isfile(os.path.join(image_dir, f))]
    files_sorted_by_mtime = sorted(files, key=lambda x: os.path.getmtime(os.path.join(image_dir, x)), reverse=True)

    original_files = [f"files/images/{f}" for f in files_sorted_by_mtime if 'original' in f]
    processed_files = [f"files/images/{f}" for f in files_sorted_by_mtime if 'processed' in f]

    files_json = {
        'original': original_files,
        'processed': processed_files
    }

    return web.json_response(files_json)


async def offer_producer(request):
    if App.connection_manager.is_producer_connection_limit_reached():
        logger.error(f"Already receiving {ConnectionManager.MAX_PRODUCER_CONNECTIONS} producing video streams")
        return

    params = await request.json()
    model_id = "yolo-v8x"

    if "modelId" in params:
        model_id = params["modelId"]

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
    async def on_track(track):
        logging.info("Track %s received", track.kind)

        if track.kind == "video":
            track1 = VideoTransformTrackDebug(App.connection_manager.media_relay.subscribe(track, buffered=True),
                                              name='video_subscription')

            track2 = VideoTransformTrack(App.connection_manager.media_relay.subscribe(track, buffered=True),
                                         name='video_subscription_edge',
                                         video_transformer=YoloTransformer(model_id,
                                                                           App.detection_service))

            # video_subscription = VideoTransformTrack(*
            #     App.connection_manager.media_relay.subscribe(track, buffered=False),
            #     name='cam-edge',
            #     video_transformer=DummyFrameTransformer()
            # )
            # video_subscription_edge = VideoTransformTrack(
            #     App.connection_manager.media_relay.subscribe(track, buffered=False),
            #     name='cam-edge',
            #     video_transformer=DummyFrameTransformer()
            # )

            # video_subscription_edge = VideoTransformTrackDebug(
            #     App.connection_manager.media_relay.subscribe(track, buffered=False),
            #     name='video_subscription_edge',
            # )
            # video_subscription = VideoTransformTrackDebug(
            #     App.connection_manager.media_relay.subscribe(track, buffered=False),
            #     name='video_subscription',
            # )

            # video_subscription_edge = App.connection_manager.media_relay.subscribe(
            #     VideoTransformTrackDebug(relayed_track, name='video_subscription_edge'), buffered=True)
            #
            # video_subscription = App.connection_manager.media_relay.subscribe(
            #     VideoTransformTrackDebug(relayed_track, name='video_subscription'),
            #     buffered=True)

            # video_subscription = VideoTransformTrackDebug(relayed_track, name='video_subscription')
            # video_subscription_edge = VideoTransformTrackDebug(relayed_track, name='video_subscription_edge')

            # video_subscription_edge = App.connection_manager.media_relay.subscribe(track, buffered=True)
            # video_subscription_edge = VideoTransformTrack(
            #     App.connection_manager.media_relay.subscribe(track, buffered=False),
            #     name='cam-edge',
            #     video_transformer=YoloTransformer(App.detection_service))

            # video_subscription_edge = VideoTransformTrack(
            #     App.connection_manager.media_relay.subscribe(track, buffered=False),
            #     name='cam-edge',
            #     video_transformer=DummyFrameTransformer())

            # video_subscription_edge = VideoTransformTrack(App.connection_manager.media_relay.subscribe(track),
            #                                               name='cam-edge',
            #                                               video_transformer=UnetTransformer(App.detection_service,
            #                                                                                 confidence_threshold=0.51))

            # Needed to start Video Tracks and analytics
            blackhole1 = MediaBlackhole()
            blackhole1.addTrack(App.connection_manager.media_relay.subscribe(track1))
            await blackhole1.start()

            blackhole2 = MediaBlackhole()
            blackhole2.addTrack(App.connection_manager.media_relay.subscribe(track2))
            await blackhole2.start()

            video_records_dir = os.path.join(AppConfig.records_directory(), "videos")
            Path.mkdir(Path(video_records_dir), exist_ok=True, parents=True)

            # recorder1 = MediaRecorder(
            #     os.path.join(video_records_dir, time.strftime('%Y%m%d-%H_%M_%S') + "-track-1.mp4"))
            # recorder1.addTrack(App.connection_manager.media_relay.subscribe(track1))
            # await recorder1.start()
            #
            # recorder2 = MediaRecorder(
            #     os.path.join(video_records_dir, time.strftime('%Y%m%d-%H_%M_%S') + "-track-2.mp4"))
            # recorder2.addTrack(App.connection_manager.media_relay.subscribe(track2))
            # await recorder2.start()

            peer_connection.subscriptions.append(track1)
            peer_connection.subscriptions.append(track2)

        @track.on("ended")
        async def on_ended():
            # await recorder1.stop()
            # await recorder2.stop()
            logging.info("Track %s ended", track.kind)

    # handle offer
    await peer_connection.setRemoteDescription(offer)
    return await App.connection_manager.create_sdp_response_for_peer_connection(peer_connection)


async def offer_consumer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    consumer_peer_connection = App.connection_manager.create_peer_connection(connection_type="consumer")

    producer_peer_connection = App.connection_manager.get_primary_producer_connection()

    blackhole = MediaBlackhole()
    blackhole.addTrack(
        App.connection_manager.media_relay.subscribe(producer_peer_connection.subscriptions[0], buffered=False))
    await blackhole.start()

    # track1 = App.connection_manager.media_relay.subscribe(producer_peer_connection.subscriptions[0], buffered=False)
    track2 = App.connection_manager.media_relay.subscribe(producer_peer_connection.subscriptions[1], buffered=False)

    # consumer_peer_connection.addTrack(track1)
    consumer_peer_connection.addTrack(track2)
    ConnectionManager.force_codec(consumer_peer_connection, "video/H264")

    await consumer_peer_connection.setRemoteDescription(offer)
    return await App.connection_manager.create_sdp_response_for_peer_connection(consumer_peer_connection)


async def on_shutdown(app):
    App.telemetry_service.shutdown()
    await App.connection_manager.shutdown()
    loop = asyncio.get_event_loop()
    pending = asyncio.all_tasks(loop=loop)
    for task in pending:
        task.cancel()
        try:
            # Await the task to handle the cancellation properly
            logging.info(f"Awaiting {task.get_name()}")
            await task
            logging.info(f"{task.get_name()}: {task.done()}")
        except asyncio.CancelledError:
            logging.info(f"Task [{task.get_name()}] cancellation handled")

    pending = asyncio.all_tasks(loop=loop)
    for task in pending:
        await task


def init_app_services(stun_server):
    App.connection_manager = ConnectionManager(stun_server)
    App.telemetry_service = TelemetryService(App.connection_manager)
    App.auth_service = Auth(os.path.join(AppConfig.root_path, "auth.json"))


def photo_index_page(request):
    path = os.path.join(AppConfig.root_path, "records/images")
    files = sorted(os.listdir(path), reverse=True)  # Customize your sorting here
    html_content = "<html><body><ul>"

    for file in files:
        html_content += f'<li><a href="/files/images/{file}">{file}</a></li>'

    html_content += "</ul></body></html>"
    return web.Response(content_type="text/html", text=html_content)


def init_web_app():
    if torch.cuda.is_available():
        logging.info("CUDA is available 🚀🚀🚀")
    else:
        logging.info("CUDA is not available 🐌🐌🐌")

    loop = asyncio.get_event_loop()
    loop.set_debug(True)

    app = web.Application()
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(os.path.join(AppConfig.root_path, "html-files/templates")))

    app.middlewares.append(App.auth_service.basic_auth_middleware)

    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", tailwind)
    app.router.add_get("/app.js", javascript)
    app.router.add_get("/style.css", css)

    app.router.add_static("/images", os.path.join(AppConfig.root_path, "html-files/images"))

    app.router.add_get("/image-files", photo_index_page)

    app.router.add_static(prefix="/files/images", path=os.path.join(AppConfig.root_path, "records/images"))

    app.router.add_get("/image-analyzer", image_analyzer_html)
    app.router.add_post("/image-analyzer-upload", image_analyzer_upload_endpoint)

    app.router.add_get("/image-detection", image_detection_html)
    app.router.add_get("/api/photo-files", photos_api_endpoint)

    app.router.add_get("/api/models", models_api_endpoint)

    app.router.add_post("/offer", offer_producer)
    app.router.add_post("/viewonly", offer_consumer)

    return app


async def on_startup(app):
    asyncio.create_task(App.telemetry_service.start())


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
    # global profiler
    # profiler = cProfile.Profile()

    # profiler.enable()
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
    parser.add_argument("--stun-server", help="STUN Server", type=str, default="stun:stun.l.google.com:19302")

    global args
    args = parser.parse_args()

    init_app_services(args.stun_server)
    logging.info(f"Using STUN SERVER: {args.stun_server}")
    check_if_user_mode()

    # AppConfig.damage_detection_model_file = args.damage_model_file
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

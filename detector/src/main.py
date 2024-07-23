import cv2

from detector.src import detector

if __name__ == "__main__":
    vid = cv2.VideoCapture("data/movie_1920x1080.mp4")
    if not vid.isOpened():
        print("Cannot open camera")
        exit(1)

    while vid.isOpened():
        _, frame = vid.read()
        # pixel values normalization
        # img = (frame - np_mean) / np_std

        detector.to("cuda")
        result = detector(frame, conf_th=0.1, device="cuda")[0]
        # result = detection_module.predict_from_numpy(
        #     img, conf_th=threshold_confidence
        # )

        print(f"{len(result['scores'])} objects detected.")
        print("xywh coordinates:", result["boxes"])
        print("Object certainty:", result["scores"])
        print("Classes:", result["labels"])

    vid.release()

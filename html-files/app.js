// data channel


$(document).ready(() => {
    let processing = false
    let processedPhotoFileName = ""
    let latestPhotoOriginal
    let latestPhotoProcessed

    function fetchModels() {
        $.ajax("/api/models", {
            type: 'GET', success: (data) => {
                console.log(data)
                for (const [index, model] of data.entries()) {
                    const selected = index === 0
                    const $html = $(renderModelOption(model.id, model.name, selected))
                    if (selected) {
                        $html.find('input[type="radio"]').prop('checked', true);
                    }
                    $("#modelOptionsDiv").append($html)
                }
            }
        })
    }


    function onOriginalPhotoReceived() {
        processing = true
        const detectionImageOriginalElement = $("#detectionImageOriginal")
        const detectionImageProcessed = $("#detectionImageProcessed")
        detectionImageOriginalElement.off("load")
        $("#processingOverlay").show()
        detectionImageProcessed.addClass('blinking');
    }

    function onProcessedPhotoReceived() {
        processing = false
        const detectionImageProcessed = $("#detectionImageProcessed")
        detectionImageProcessed.off("load")
        detectionImageProcessed.removeClass('blinking');
        $("#processingOverlay").hide()
    }

    async function waitForImageToLoad(imgJqueryObject) {
        const imgElement = imgJqueryObject[0]
        return new Promise((resolve, reject) => {
            // Check if the image is already loaded (for cached images)
            if (imgElement.complete && imgElement.naturalHeight !== 0) {
                resolve('Image already loaded.');
            } else {
                // Add an event listener for the 'load' event
                imgElement.onload = () => {
                    resolve('Image loaded successfully.');
                };
                // Add an error listener in case the image fails to load
                imgElement.onerror = () => {
                    reject('Image failed to load.');
                };
            }
        })
    }

    async function checkOriginalImageElement(data) {
        return new Promise((resolve, reject) => {
            if (data.original && data.original[0]) {
                if (!processing && latestPhotoOriginal !== data.original[0]) {
                    firstLoad = latestPhotoOriginal === undefined
                    latestPhotoOriginal = data.original[0]
                    processedPhotoFileName = latestPhotoOriginal
                    if (!firstLoad) {
                        const toast = $('#toast');
                        toast.addClass('toast-show')
                        setTimeout(() => {
                            toast.removeClass('toast-show');
                        }, 5000);
                        const detectionImageOriginalElement = $("#detectionImageOriginal")
                        const detectionImageProcessed = $("#detectionImageProcessed")

                        detectionImageOriginalElement.on("load", onOriginalPhotoReceived)
                        detectionImageOriginalElement.attr('src', latestPhotoOriginal)
                        detectionImageProcessed.attr('src', latestPhotoOriginal)

                        return resolve(
                            waitForImageToLoad(detectionImageOriginalElement)
                                .then(
                                    () => waitForImageToLoad(detectionImageProcessed)
                                )
                        )
                    }
                }
            }
            return resolve()
        })
    }

    async function checkProcessedImageElement(data) {
        return new Promise((resolve, reject) => {
            if (data.processed && data.processed[0]) {
                if (latestPhotoProcessed !== data.processed[0]) {
                    firstLoad = latestPhotoProcessed === undefined
                    latestPhotoProcessed = data.processed[0]
                    if (!firstLoad && latestPhotoProcessed === latestPhotoOriginal.replace("original", "processed")) {
                        const detectionImageProcessed = $("#detectionImageProcessed")
                        detectionImageProcessed.on("load", onProcessedPhotoReceived)
                        detectionImageProcessed.attr('src', latestPhotoProcessed)
                        const result = waitForImageToLoad(detectionImageProcessed)
                        return resolve(result)
                    }
                }
            }
            return resolve()
        })
    }

    async function getLatestPhoto(callback) {
        return new Promise((resolve, reject) => {
            $.ajax("/api/photo-files", {
                type: 'GET', success: (data) => {
                    if (data) {
                        return resolve(checkOriginalImageElement(data)
                            .then(
                                () => checkProcessedImageElement(data)
                            )
                        )
                    }
                    return resolve()
                }
            })
        })
    }

    function startPhotoCheck() {
        asyncInterval(getLatestPhoto, 1000)

        // setInterval(() => {
        //     getLatestPhoto()
        // }, 1000)

    }

    if ($('#detectionImageOriginal')) {
        // getLatestPhoto(() => {
        //
        // })
        startPhotoCheck()
    }

    function renderModelOption(modelId, modelName, selected) {
        return `
        <label class="flex items-center space-x-2">
            <input type="radio" name="modelId" value="${modelId}" class="form-radio text-blue-600">
            <span>${modelName}</span>
        </label>
        `
    }

    fetchModels()


    let dcInterval
    let time_start = null

    let dataConnections = []
    let peerConnections = []

    let connected = false
    const numberOfTracks = 2

    function createPeerConnection(useTestVideo = false) {
        // const config = {
        //     sdpSemantics: 'unified-plan'
        // };

        var config = {
            sdpSemantics: 'unified-plan'
        };

        const pc = new RTCPeerConnection(config)

        pc.ondatachannel = (channelEvt) => {
            console.log(channelEvt)
            channelEvt.channel.addEventListener('open', () => {

            })
            channelEvt.channel.addEventListener('message', (messageEvt) => {
                const messageJson = JSON.parse(messageEvt.data)
                console.log(messageJson)

                if (messageJson.type === 'rtt-packet') {
                    if (channelEvt.channel.readyState === "open") {
                        channelEvt.channel.send(messageEvt.data)
                    }
                }

                if (messageJson.type === 'telemetry') {
                    $('#rttCamera').text(`${parseInt(messageJson.rttProducer)} ms`)
                    $('#rttValue').text(`${parseInt(messageJson.rttConsumer)} ms`)
                    $('#fpsDecodingValue').text(`${parseInt(messageJson.fpsDecoding)}`)
                    $('#fpsDetectionValue').text(`${parseFloat(messageJson.fpsDetection).toFixed(1)}`)
                    $('#detectionTimeValue').text(`${parseInt(messageJson.detectionTime)} ms`)
                }
            });
        }

        pc.addEventListener('datachannel', (evt) => {
            console.log(evt.channel.label)
        })

        pc.addEventListener('icegatheringstatechange', (evt) => {
            console.log("ICE Gathering: " + pc.iceGatheringState);
        })

        pc.addEventListener('iceconnectionstatechange', (evt) => {
            console.log("ICE Connection: " + pc.iceConnectionState);
        })

        pc.addEventListener('signalingstatechange', (evt) => {
            console.log("Signaling state: " + pc.signalingState);
        })

        pc.addEventListener('connectionstatechange', (evt) => {
            console.log(evt)
        })
        pc.addEventListener('track', (evt) => {
            console.log(evt.transceiver.mid)
            const constraints = {};

            if (evt.track.kind === 'video') {
                evt.track.applyConstraints(constraints)
                    .then(() => {
                        if (evt.transceiver.mid === "1") {
                            document.getElementById(useTestVideo ? 'video03' : 'video01').srcObject = new MediaStream([evt.track]);
                        }
                        if (evt.transceiver.mid === "0") {
                            document.getElementById(useTestVideo ? 'video04' : 'video02').srcObject = new MediaStream([evt.track]);
                        }
                    })
                    .catch((error) => console.log(error))
            }
        });

        console.log(pc)
        return pc
    }

    const current_stamp = () => {
        if (time_start === null) {
            time_start = new Date().getTime();
            return 0;
        } else {
            return new Date().getTime() - time_start;
        }
    };

    function createDataConnection(pc) {
        const dc = pc.createDataChannel('chat');
        dc.addEventListener('close', () => {
            clearInterval(dcInterval);
            console.log("Datachannel - close")
        });

        dc.addEventListener('open', () => {
            console.log("Datachannel - open")
            dcInterval = setInterval(() => {
                let message = {
                    type: "rtt", timestamp: current_stamp()
                }
                dc.send(JSON.stringify(message));
            }, 1000);
        });

        dc.addEventListener('message', (evt) => {
            const messageJson = JSON.parse(evt.data)
            console.log(messageJson)

            if (messageJson.type === 'rtt') {
                let elapsed_ms = current_stamp() - parseInt(messageJson.timestamp, 10);
                $('#rttValue').text(`${elapsed_ms} ms`)
            }

            //{type: 'telemetry', rttCamera: 4, fpsDecoding: 30.057103085584057, fpsDetection: 0, detectionTime: 1721821298844658700}
            if (messageJson.type === 'telemetry') {
                $('#rttCamera').text(`${parseInt(messageJson.rttCamera)} ms`)
                $('#fpsDecodingValue').text(`${parseInt(messageJson.fpsDecoding)}`)
                $('#fpsDetectionValue').text(`${parseInt(messageJson.fpsDetection)}`)
            }
        });

        return dc
    }

    async function negotiate(pc) {
        for (let i = 0; i < numberOfTracks; i++) {
            pc.addTransceiver('video', {direction: 'recvonly'});
        }

        // pc.createDataChannel('telemetry')
        let offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        let response = await fetch("/viewonly", {
            method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
                sdp: pc.localDescription.sdp, type: pc.localDescription.type
            })
        });

        let answer = await response.json();
        await pc.setRemoteDescription(new RTCSessionDescription(answer));
    }

    function closeDataConnections(dataConnections) {
        dataConnections.forEach(dataConnection => {
            dataConnection.close()
        })
    }

    function closePeerConnections(pcs) {
        pcs.forEach(pc => {
            if (pc.getTransceivers) {
                pc.getTransceivers().forEach((transceiver) => {
                    if (transceiver.stop) {
                        transceiver.stop();
                    }
                });

                pc.getSenders().forEach((sender) => {
                    sender.track?.stop();
                });

                setTimeout(() => {
                    pc.close();
                }, 500);
            }
        })
    }

    function onClickLive() {
        if (!connected) {
            document.getElementById("btnConnectLive").textContent = "Disconnect"
            let pc1 = createPeerConnection();
            dataConnections.push(createDataConnection(pc1))
            peerConnections.push(pc1)
            negotiate(pc1).then((pc) => {
                console.log(pc)
            })
            connected = true
        } else {
            document.getElementById("btnConnectLive").textContent = "Connect"
            closeDataConnections(dataConnections)
            dataConnections = []
            closePeerConnections(peerConnections)
            peerConnections = []
            connected = false
        }
    }

    $("#btnConnectLive").click(onClickLive)

    $('#imageInput').on('change', function () {
        $('#response').html('<p></p>')
        const file = this.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function (e) {
                $('#previewImage').attr('src', e.target.result);
                $('#previewContainer').show();
            }
            reader.readAsDataURL(file);
        }
    });

    $('#uploadForm').on('submit', function (e) {
        e.preventDefault();
        const selectedValue = $('input[name="modelId"]:checked').val();
        $('#submitButton').text("Analyzing...")
        $('#submitButton').prop('disabled', true)
        const imageFile = $('#imageInput')[0].files[0];
        const reader = new FileReader();
        reader.onloadend = function () {
            const base64String = reader.result.replace("data:", "").replace(/^.+,/, "");
            console.log(base64String);

            $.ajax({
                url: '/image-analyzer-upload', // Replace with your REST API endpoint
                type: 'POST',
                data: JSON.stringify({image: base64String, modelId: selectedValue}),
                contentType: 'application/json',
                success: function (response) {
                    const base64Image = response.image;
                    const imgSrc = 'data:image/jpeg;base64,' + base64Image;
                    $('#previewImage').attr('src', imgSrc);
                    $('#response').html('<p class="text-green-500">Image processed successfully!</p>');
                    $('#submitButton').text("Analyze")
                    $('#submitButton').prop('disabled', false)
                },
                error: function (error) {
                    $('#response').html('<p class="text-red-500">Failed to upload image.</p>');
                    $('#submitButton').text("Analyze")
                    $('#submitButton').prop('disabled', false)
                }
            });
        }
        reader.readAsDataURL(imageFile);
    });
})

function asyncInterval(fn, delay) {
    let isRunning = false;

    const interval = async () => {
        if (isRunning) return;

        isRunning = true;
        try {
            await fn();  // Wait for the Promise to resolve
        } catch (err) {
            console.error('Error in interval function:', err);
        }
        isRunning = false;

        setTimeout(interval, delay);  // Schedule the next call after the delay
    };

    interval();  // Start the interval

    return () => {
        isRunning = false;
    };  // Return a function to cancel the interval
}

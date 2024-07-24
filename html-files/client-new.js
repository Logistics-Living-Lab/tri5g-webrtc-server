// data channel


$(document).ready(() => {
    console.log("Ready!")

    let dcInterval
    let time_start = null

    let dataConnections = []
    let peerConnections = []

    let connected = false
    let connectedTestVideo = false

    const numberOfTracks = 2

    function createPeerConnection(useTestVideo = false) {
        let config = {
            sdpSemantics: 'unified-plan'
        };

        const pc = new RTCPeerConnection(config)
        // addEventListeners(pc)

        // connect audio / video
        pc.addEventListener('track', (evt) => {
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
        return pc;
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
                    type: "rtt",
                    timestamp: current_stamp()
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

    function addEventListeners(pc) {
        pc.addEventListener('icegatheringstatechange', () => {
            iceGatheringLog.textContent += ' -> ' + pc.iceGatheringState;
        }, false);
        iceGatheringLog.textContent = pc.iceGatheringState;

        pc.addEventListener('iceconnectionstatechange', () => {
            iceConnectionLog.textContent += ' -> ' + pc.iceConnectionState;
        }, false);
        iceConnectionLog.textContent = pc.iceConnectionState;

        pc.addEventListener('signalingstatechange', () => {
            signalingLog.textContent += ' -> ' + pc.signalingState;
        }, false);
        signalingLog.textContent = pc.signalingState;
    }

    function negotiate(pc, channel = "") {
        for (let i = 0; i < numberOfTracks; i++) {
            pc.addTransceiver('video', {direction: 'recvonly'});
        }

        pc.getTransceivers().forEach(transceiver => {
            // transceiver.setCodecPreferences()
        })

        return pc.createOffer().then((offer) => {
            // Iterate over the SDP lines to find the video media section
            let sdpLines = offer.sdp.split('\r\n');
            let isVideoSection = false;
            let h264Added = false;
            const maxBitrate = 40000000
            for (let i = 0; i < sdpLines.length; i++) {
                if (sdpLines[i].startsWith('m=video')) {
                    isVideoSection = true;
                } else if (isVideoSection && sdpLines[i].startsWith('a=rtpmap')) {
                    // Add H.264 codec parameters if VP8 or VP9 is found
                    if (sdpLines[i].includes('VP8') || sdpLines[i].includes('VP9')) {
                        sdpLines.splice(i + 1, 0, `a=fmtp:96 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42e01f`);
                        h264Added = true;
                    }
                } else if (isVideoSection && h264Added && sdpLines[i].startsWith('a=rtcp-fb')) {
                    // Add max bitrate attribute after H.264 parameters
                    sdpLines.splice(i + 1, 0, `a=max-bitrate:${maxBitrate}`);
                    break;
                }
            }

            // Update the SDP offer with modified lines
            const modifiedSdpOffer = sdpLines.join('\r\n');
            offer.sdp = modifiedSdpOffer

            return pc.setLocalDescription(offer);
        }).then(() => {
            // wait for ICE gathering to complete
            return new Promise((resolve) => {
                if (pc.iceGatheringState === 'complete') {
                    resolve();
                } else {
                    function checkState() {
                        if (pc.iceGatheringState === 'complete') {
                            pc.removeEventListener('icegatheringstatechange', checkState);
                            resolve();
                        }
                    }

                    pc.addEventListener('icegatheringstatechange', checkState);
                }
            });
        }).then(() => {
            let offer = pc.localDescription;
            // const maxBitrate = 100000000
            // const sdpWithMaxBitrate = offer.sdp.replace(/a=mid:video\r?\n/g, '$&a=recvonly\r\na=fmtp:96 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42e01f\r\na=max-bitrate:' + maxBitrate + '\r\n');
            return fetch('/viewonly', {
                body: JSON.stringify({
                    sdp: offer.sdp,
                    type: offer.type,
                    video_transform: '',
                    channel: channel
                }),
                headers: {
                    'Content-Type': 'application/json'
                },
                method: 'POST'
            });
        }).then((response) => {
            return response.json();
        }).then((answer) => {
            return pc.setRemoteDescription(answer);
        }).catch((e) => {
            alert(e);
        });
    }

    function onClickTestVideo() {
        if (!connectedTestVideo) {
            document.getElementById("btnConnectTestVideo").textContent = "Disconnect"
            let pc1 = createPeerConnection(true);
            pcsTest.push(pc1)
            negotiate(pc1, 'test-video');
            connectedTestVideo = true
        } else {
            document.getElementById("btnConnectTestVideo").textContent = "Connect"
            closeDataConnection(dcTest)
            closePeerConnections(pcsTest)
            pcsTest = []
            connectedTestVideo = false
        }
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
            negotiate(pc1);
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
})

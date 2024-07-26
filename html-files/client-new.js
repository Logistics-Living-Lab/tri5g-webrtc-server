// data channel


$(document).ready(() => {
    let dcInterval
    let time_start = null

    let dataConnections = []
    let peerConnections = []

    let connected = false
    const numberOfTracks = 2

    function createPeerConnection(useTestVideo = false) {
        const pc = new RTCPeerConnection()
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
            console.log("Test")
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
})

// data channel
let dcLive = null
let dcTest = null
let pcsLive = []
let pcsTest = []

let connected = false
let connectedTestVideo = false

const numberOfTracks = 2

function createPeerConnection(useTestVideo = false) {
    let config = {
        sdpSemantics: 'unified-plan'
    };

    const pc = new RTCPeerConnection(config)


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

function closeDataConnection(dc) {
    if (dc) {
        dc.close();
    }
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
        pcsLive.push(pc1)
        negotiate(pc1);
        connected = true
    } else {
        document.getElementById("btnConnectLive").textContent = "Connect"
        closeDataConnection(dcLive)
        closePeerConnections(pcsLive)
        pcsLive = []
        connected = false
    }
}

// document.getElementById('video01').addEventListener('loadedmetadata', () => {
//     // Retrieve the width and height of the video
//     const width = document.getElementById('video01').videoWidth;
//     const height = document.getElementById('video01').videoHeight;
//     console.log(document.getElementById('video01'))
// })

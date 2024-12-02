const socket = new WebSocket('ws://localhost:3000');

let localStream;
let remoteStream;
let peerConnection;
const configuration = {
  iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
};

let peerName = ''; // Store the peer's name
let userName = ''; // Store the user's name
let micPermissionGranted = false;
let isInitiator = false; // Flag to determine if this client should create the offer

// Set up the WebSocket events
socket.onopen = () => {
  console.log('Connected to WebSocket server');
  document.getElementById('status').textContent = 'Connected to WebSocket';
};

socket.onmessage = async (event) => {
  const data = JSON.parse(event.data);
  console.log('Message from server:', data);

  if (data.action === 'nameSubmitted') {
    userName = document.getElementById('nameInput').value.trim();
    document.getElementById('nameSection').style.display = 'none';
    document.getElementById('queueSection').style.display = 'block';
    document.getElementById('status').textContent = data.message;
    // Display user's own average rating
    document.getElementById('ratingDisplay').textContent = `Your average rating: ${data.avgRating}`;

    // Request microphone access
    try {
      localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      document.getElementById('localAudio').srcObject = localStream;
      micPermissionGranted = true;
    } catch (err) {
      alert('Microphone access is required to join the queue.');
      micPermissionGranted = false;
    }

  } else if (data.action === 'queueJoined') {
    document.getElementById('status').textContent = data.message;
    document.getElementById('joinButton').style.display = 'none'; // Hide "Join Queue" button
  } else if (data.action === 'timerUpdate') {
    document.getElementById('timer').textContent = data.message;
  } else if (data.action === 'startMatch') {
    document.getElementById('status').textContent = data.message;
    document.getElementById('timer').style.display = 'none'; // Hide timer during countdown
  } else if (data.action === 'countdown') {
    document.getElementById('status').textContent = data.message;
  } else if (data.action === 'startTimer') {
    // Show the timer after countdown
    document.getElementById('timer').style.display = 'block';
    document.getElementById('status').textContent = ''; // Clear status message
  } else if (data.action === 'matched') {
    document.getElementById('status').textContent = data.message;
    document.getElementById('endCall').style.display = 'block';  // Show "End Call" button
    peerName = data.peerName; // Store the peer's name
    isInitiator = data.initiator; // Get initiator flag from server
    await startCall();
  } else if (data.action === 'offer') {
    handleOffer(data.message);
  } else if (data.action === 'answer') {
    handleAnswer(data.message);
  } else if (data.action === 'candidate') {
    handleCandidate(data.message);
  } else if (data.action === 'survey') {
    showSurvey(data.message);
  } else if (data.action === 'ratingSubmitted') {
    document.getElementById('status').textContent = data.message;
  } else if (data.action === 'yourRatingUpdated') {
    // Update user's own average rating
    document.getElementById('ratingDisplay').textContent = `Your average rating: ${data.avgRating}`;
    // No alert needed as per your request
  } else if (data.action === 'askToRejoin') {
    document.getElementById('rejoinSection').style.display = 'block';
  } else if (data.action === 'endCall') {
    document.getElementById('status').textContent = data.message;
    document.getElementById('endCall').style.display = 'none'; // Hide "End Call" button
    document.getElementById('timer').style.display = 'none';   // Hide timer
    document.getElementById('timer').textContent = '';         // Clear timer text
    // Close the peer connection
    if (peerConnection) {
      peerConnection.close();
      peerConnection = null;
    }
    remoteStream = null; // Reset remote stream
    // Stop local stream (do not stop to keep mic access for next match)
    // localStream will persist for the next call
  } else if (data.action === 'peerDisconnected') {
    alert(data.message);
    // Handle peer disconnection
    if (peerConnection) {
      peerConnection.close();
      peerConnection = null;
    }
    // Do not stop local stream
  } else if (data.action === 'error') {
    alert(data.message);
  }
};

socket.onclose = () => {
  console.log('Disconnected from server');
  document.getElementById('status').textContent = 'Disconnected';
};

socket.onerror = (error) => {
  console.error('WebSocket error:', error);
  document.getElementById('status').textContent = 'Connection error';
};

// Handle name input and Submit Name
document.getElementById('nameInput').addEventListener('input', (e) => {
  if (e.target.value.trim() !== '') {
    document.getElementById('submitName').style.display = 'block';
  } else {
    document.getElementById('submitName').style.display = 'none';
  }
});

document.getElementById('submitName').addEventListener('click', () => {
  const name = document.getElementById('nameInput').value.trim();
  if (name && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ action: 'submitName', name: name }));
  }
});

// Handle "Join Queue" Button click
document.getElementById('joinButton').addEventListener('click', () => {
  if (micPermissionGranted && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ action: 'joinQueue' }));
    document.getElementById('status').textContent = 'Joining queue...';
    document.getElementById('joinButton').style.display = 'none'; // Hide "Join Queue" button
  } else {
    alert('Microphone access is required to join the queue.');
  }
});

// Handle Rejoin Queue Button click
document.getElementById('rejoinButton').addEventListener('click', () => {
  document.getElementById('rejoinSection').style.display = 'none';
  if (socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ action: 'rejoinQueue' }));
    document.getElementById('status').textContent = 'Rejoining queue...';
  }
});

// Handle End Call button
document.getElementById('endCall').addEventListener('click', () => {
  socket.send(JSON.stringify({ action: 'endCall' }));
  document.getElementById('endCall').style.display = 'none';
  document.getElementById('timer').style.display = 'none';
  // Close the peer connection
  if (peerConnection) {
    peerConnection.close();
    peerConnection = null;
  }
});

// Handle survey submission
document.getElementById('submitSurvey').addEventListener('click', () => {
  const rating = parseInt(document.getElementById('ratingInput').value, 10);
  if (rating >= 1 && rating <= 5) {
    socket.send(JSON.stringify({ action: 'submitRating', rating: rating }));
    document.getElementById('survey').style.display = 'none';
    document.getElementById('ratingInput').value = ''; // Reset input
  } else {
    alert('Please enter a valid rating between 1 and 5.');
  }
});

function showSurvey(message) {
  document.getElementById('surveyPrompt').textContent = message;
  document.getElementById('survey').style.display = 'block';
}

async function startCall() {
  document.getElementById('status').textContent = `Matched with ${peerName}`;

  // Create peer connection
  peerConnection = new RTCPeerConnection(configuration);

  // Add local stream to peer connection
  localStream.getTracks().forEach((track) => {
    peerConnection.addTrack(track, localStream);
  });

  // Handle remote stream
  peerConnection.ontrack = (event) => {
    if (!remoteStream) {
      remoteStream = new MediaStream();
      document.getElementById('remoteAudio').srcObject = remoteStream;
    }
    remoteStream.addTrack(event.track);
  };

  // Handle ICE candidates
  peerConnection.onicecandidate = (event) => {
    if (event.candidate) {
      socket.send(JSON.stringify({
        action: 'candidate',
        message: event.candidate
      }));
    }
  };

  if (isInitiator) {
    // Create and send offer
    const offer = await peerConnection.createOffer();
    await peerConnection.setLocalDescription(offer);
    socket.send(JSON.stringify({
      action: 'offer',
      message: offer
    }));
  }
}

async function handleOffer(offer) {
  if (!peerConnection) {
    // Create peer connection
    peerConnection = new RTCPeerConnection(configuration);

    // Add local stream to peer connection
    localStream.getTracks().forEach((track) => {
      peerConnection.addTrack(track, localStream);
    });

    // Handle remote stream
    peerConnection.ontrack = (event) => {
      if (!remoteStream) {
        remoteStream = new MediaStream();
        document.getElementById('remoteAudio').srcObject = remoteStream;
      }
      remoteStream.addTrack(event.track);
    };

    // Handle ICE candidates
    peerConnection.onicecandidate = (event) => {
      if (event.candidate) {
        socket.send(JSON.stringify({
          action: 'candidate',
          message: event.candidate
        }));
      }
    };
  }

  await peerConnection.setRemoteDescription(new RTCSessionDescription(offer));
  const answer = await peerConnection.createAnswer();
  await peerConnection.setLocalDescription(answer);
  socket.send(JSON.stringify({
    action: 'answer',
    message: answer
  }));
}

async function handleAnswer(answer) {
  await peerConnection.setRemoteDescription(new RTCSessionDescription(answer));
}

async function handleCandidate(candidate) {
  try {
    await peerConnection.addIceCandidate(new RTCIceCandidate(candidate));
  } catch (err) {
    console.error('Error adding received ice candidate', err);
  }
}

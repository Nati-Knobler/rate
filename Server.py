import asyncio
import websockets
import json

# Store connected clients, queue, user ratings, and matches
queue = []
user_ratings = {}
matches = {}
connected_users = {}  # Mapping from usernames to user dictionaries

# Function to handle WebSocket connections
async def handle_connection(websocket, path=None):
    print(f"New connection from: {websocket.remote_address}")

    # Initialize user data
    user = {'socket': websocket, 'name': None, 'state': 'awaiting_name', 'peer_name': None, 'timer_task': None}
    try:
        async for message in websocket:
            data = json.loads(message)
            action = data.get('action')

            if action == 'submitName' and user['state'] == 'awaiting_name':
                user['name'] = data['name']
                user['state'] = 'ready'
                # Initialize user rating if not exists
                if user['name'] not in user_ratings:
                    user_ratings[user['name']] = []
                connected_users[user['name']] = user  # Add to connected users
                # Send user's own average rating
                avg_rating = (
                    sum(user_ratings[user['name']]) / len(user_ratings[user['name']])
                    if user_ratings[user['name']]
                    else 0.0
                )
                await websocket.send(json.dumps({
                    'action': 'nameSubmitted',
                    'message': f'Welcome, {user["name"]}!',
                    'avgRating': f'{avg_rating:.2f}'
                }))

            elif action == 'joinQueue' and user['state'] == 'ready':
                user['state'] = 'in_queue'
                queue.append(user)
                await websocket.send(json.dumps({
                    'action': 'queueJoined',
                    'message': f'You are in the queue! Your position is {len(queue)}'
                }))

                # If there are at least two people in the queue, start matchmaking
                if len(queue) >= 2:
                    user1 = queue.pop(0)
                    user2 = queue.pop(0)

                    # Update matches
                    matches[user1['socket']] = user2
                    matches[user2['socket']] = user1

                    # Notify both users that they are matched
                    await user1['socket'].send(json.dumps({
                        'action': 'matched',
                        'message': f'Hi {user1["name"]}, you are now matched with {user2["name"]}',
                        'peerName': user2['name'],
                        'initiator': True  # Designate user1 as the initiator
                    }))
                    await user2['socket'].send(json.dumps({
                        'action': 'matched',
                        'message': f'Hi {user2["name"]}, you are now matched with {user1["name"]}',
                        'peerName': user1['name'],
                        'initiator': False
                    }))

                    # Update peer names
                    user1['peer_name'] = user2['name']
                    user2['peer_name'] = user1['name']

                    # Start match logic
                    asyncio.create_task(start_match(user1, user2))

            elif action in ['offer', 'answer', 'candidate']:
                # Relay the message to the matched peer
                peer_user = matches.get(websocket)
                if peer_user:
                    await peer_user['socket'].send(json.dumps({
                        'action': action,
                        'message': data['message']
                    }))

            elif action == 'submitRating':
                rating = int(data['rating'])
                peer_name = user.get('peer_name')
                if peer_name:
                    # Store the rating under the peer's name
                    if peer_name not in user_ratings:
                        user_ratings[peer_name] = []
                    user_ratings[peer_name].append(rating)
                    avg_rating = sum(user_ratings[peer_name]) / len(user_ratings[peer_name])

                    # Notify the user that they have rated their peer
                    await websocket.send(json.dumps({
                        'action': 'ratingSubmitted',
                        'message': f"You rated {peer_name}."
                    }))

                    # If the peer is connected, send them their updated average rating
                    peer_user = connected_users.get(peer_name)
                    if peer_user:
                        peer_avg_rating = sum(user_ratings[peer_name]) / len(user_ratings[peer_name])
                        await peer_user['socket'].send(json.dumps({
                            'action': 'yourRatingUpdated',
                            'avgRating': f"{peer_avg_rating:.2f}",
                            'message': "Your average rating has been updated."
                        }))
                else:
                    await websocket.send(json.dumps({
                        'action': 'error',
                        'message': 'No peer to rate.'
                    }))

                # Ask if the user wants to join the queue again
                user['state'] = 'ready'
                await websocket.send(json.dumps({
                    'action': 'askToRejoin',
                    'message': 'Do you want to join the queue again?'
                }))

            elif action == 'endCall':
                peer_user = matches.get(websocket)
                await end_call(user, peer_user)

            elif action == 'rejoinQueue' and user['state'] == 'ready':
                # User chooses to rejoin the queue
                user['state'] = 'in_queue'
                queue.append(user)
                await websocket.send(json.dumps({
                    'action': 'queueJoined',
                    'message': f'You are back in the queue! Your position is {len(queue)}'
                }))

                # Check if we can match users
                if len(queue) >= 2:
                    user1 = queue.pop(0)
                    user2 = queue.pop(0)

                    # Update matches
                    matches[user1['socket']] = user2
                    matches[user2['socket']] = user1

                    # Notify both users that they are matched
                    await user1['socket'].send(json.dumps({
                        'action': 'matched',
                        'message': f'Hi {user1["name"]}, you are now matched with {user2["name"]}',
                        'peerName': user2['name'],
                        'initiator': True
                    }))
                    await user2['socket'].send(json.dumps({
                        'action': 'matched',
                        'message': f'Hi {user2["name"]}, you are now matched with {user1["name"]}',
                        'peerName': user1['name'],
                        'initiator': False
                    }))

                    # Update peer names
                    user1['peer_name'] = user2['name']
                    user2['peer_name'] = user1['name']

                    # Start match logic
                    asyncio.create_task(start_match(user1, user2))

        # Handle disconnection
    except websockets.ConnectionClosed:
        print(f"Connection closed: {user['name']}")
        # Clean up matches and queue
        peer_user = matches.pop(websocket, None)
        if peer_user:
            matches.pop(peer_user['socket'], None)
            await peer_user['socket'].send(json.dumps({
                'action': 'peerDisconnected',
                'message': 'Your peer has disconnected.'
            }))
    finally:
        # Remove user from queue if they disconnect
        if user in queue:
            queue.remove(user)
        # Remove from connected users
        if user['name'] in connected_users:
            del connected_users[user['name']]
        # Cancel any running timer task
        timer_task = user.get('timer_task')
        if timer_task:
            timer_task.cancel()
            user['timer_task'] = None

# Function to start the match and initiate the countdown
async def start_match(user1, user2):
    # Send initial message about match
    await user1['socket'].send(json.dumps({
        'action': 'startMatch',
        'message': 'You are connected! Get ready for the countdown.'
    }))
    await user2['socket'].send(json.dumps({
        'action': 'startMatch',
        'message': 'You are connected! Get ready for the countdown.'
    }))

    # Start countdown and timer
    asyncio.create_task(start_countdown_and_timer(user1, user2))

# Function to handle countdown and then start the timer
async def start_countdown_and_timer(user1, user2):
    # Countdown (3, 2, 1)
    for i in range(3, 0, -1):
        await user1['socket'].send(json.dumps({'action': 'countdown', 'message': f'Starting in {i}...'}))
        await user2['socket'].send(json.dumps({'action': 'countdown', 'message': f'Starting in {i}...'}))
        await asyncio.sleep(1)

    await user1['socket'].send(json.dumps({'action': 'countdown', 'message': 'Conversation starting now!'}))
    await user2['socket'].send(json.dumps({'action': 'countdown', 'message': 'Conversation starting now!'}))

    # Notify clients to show the timer
    await user1['socket'].send(json.dumps({'action': 'startTimer'}))
    await user2['socket'].send(json.dumps({'action': 'startTimer'}))

    # Start timer task and store it in users
    timer_task = asyncio.create_task(start_timer(user1, user2))
    user1['timer_task'] = timer_task
    user2['timer_task'] = timer_task

# Function to start the 5-minute timer
async def start_timer(user1, user2):
    call_time = 5 * 60  # 5 minutes in seconds
    timer_interval = 1
    try:
        while call_time > 0:
            minutes = call_time // 60
            seconds = call_time % 60
            time_left = f"{minutes}:{seconds:02d}"

            await user1['socket'].send(json.dumps({
                'action': 'timerUpdate',
                'message': f'Time left: {time_left}'
            }))
            await user2['socket'].send(json.dumps({
                'action': 'timerUpdate',
                'message': f'Time left: {time_left}'
            }))

            await asyncio.sleep(timer_interval)
            call_time -= timer_interval

        # After 5 minutes, end the call
        await end_call(user1, user2)

    except asyncio.CancelledError:
        print("Timer task cancelled")
        # Clean up if necessary
    except websockets.ConnectionClosed:
        print("Connection closed during call")
        # Clean up matches
        matches.pop(user1['socket'], None)
        matches.pop(user2['socket'], None)

# Handle end call logic
async def end_call(user1, user2):
    # Cancel timer task if running
    timer_task = user1.get('timer_task')
    if timer_task:
        timer_task.cancel()
        user1['timer_task'] = None
        user2['timer_task'] = None

    # Notify both users that the call has ended
    await user1['socket'].send(json.dumps({
        'action': 'endCall',
        'message': 'Call has ended.'
    }))
    await user2['socket'].send(json.dumps({
        'action': 'endCall',
        'message': 'Call has ended.'
    }))

    # Remove matches
    matches.pop(user1['socket'], None)
    matches.pop(user2['socket'], None)

    # Show survey
    await show_survey(user1)
    await show_survey(user2)

# Function to display the survey after a call ends
async def show_survey(user):
    # Ask for a rating
    await user['socket'].send(json.dumps({
        'action': 'survey',
        'message': f'Please rate your match, {user["peer_name"]}, from 1 to 5.'
    }))
    user['state'] = 'awaiting_rating'  # Update user state

# Main function to start the WebSocket server
async def main():
    async with websockets.serve(handle_connection, "localhost", 3000):
        print("WebSocket server running on ws://localhost:3000")
        await asyncio.Future()  # Run forever

# Run the server
if __name__ == "__main__":
    asyncio.run(main())

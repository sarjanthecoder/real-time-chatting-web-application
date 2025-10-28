import asyncio
import websockets
import json
import logging

logging.basicConfig(level=logging.INFO)

# Stores connected users {user_id: websocket_connection}
connected_users = {}

async def handler(websocket, path):
    """Handles incoming WebSocket connections and messages."""
    user_id = None
    try:
        # First message should be for registration
        message = await websocket.recv()
        data = json.loads(message)
        if data.get('type') == 'register':
            user_id = data.get('userId')
            if user_id and user_id not in connected_users:
                connected_users[user_id] = websocket
                logging.info(f"User '{user_id}' registered and connected.")
                await websocket.send(json.dumps({"type": "register_ok"}))
            else:
                logging.warning(f"Registration failed for user: {user_id}")
                await websocket.send(json.dumps({"type": "error", "message": "Invalid or duplicate user ID"}))
                await websocket.close()
                return
        else:
            logging.warning("First message was not register type.")
            await websocket.close()
            return

        # Listen for subsequent messages (offer, answer, candidate, etc.)
        async for message in websocket:
            try:
                data = json.loads(message)
                target_user_id = data.get('targetUserId')
                
                if target_user_id and target_user_id in connected_users:
                    target_ws = connected_users[target_user_id]
                    # Forward the message to the target user
                    # Add sender information so the receiver knows who it's from
                    data['senderUserId'] = user_id 
                    await target_ws.send(json.dumps(data))
                    logging.info(f"Forwarded message from '{user_id}' to '{target_user_id}': {data.get('type')}")
                else:
                    logging.warning(f"Target user '{target_user_id}' not found or not connected for message from '{user_id}'.")
                    # Optionally send an error back to the sender
                    # await websocket.send(json.dumps({"type": "error", "message": f"User {target_user_id} not available"}))

            except json.JSONDecodeError:
                logging.error(f"Received invalid JSON from {user_id}: {message}")
            except Exception as e:
                logging.error(f"Error processing message from {user_id}: {e}")

    except websockets.exceptions.ConnectionClosedOK:
        logging.info(f"Connection closed normally for user '{user_id}'.")
    except websockets.exceptions.ConnectionClosedError as e:
        logging.error(f"Connection closed with error for user '{user_id}': {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred for user '{user_id}': {e}")
    finally:
        # Unregister user on disconnect
        if user_id and user_id in connected_users:
            del connected_users[user_id]
            logging.info(f"User '{user_id}' disconnected and unregistered.")

async def main():
    # Start the WebSocket server on localhost, port 8765
    async with websockets.serve(handler, "localhost", 8765):
        logging.info("Signaling server started on ws://localhost:8765")
        await asyncio.Future() # Run forever

if __name__ == "__main__":
    asyncio.run(main())
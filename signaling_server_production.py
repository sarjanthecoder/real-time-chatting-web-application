import asyncio
import websockets
import json
import logging
import os
from aiohttp import web

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Get port from environment variable (Render sets this automatically)
PORT = int(os.environ.get('PORT', 8765))

# Stores connected users {user_id: websocket_connection}
connected_users = {}

async def websocket_handler(websocket):
    """Handles incoming WebSocket connections and messages."""
    user_id = None
    try:
        # First message should be for registration
        message = await websocket.recv()
        data = json.loads(message)
        if data.get('type') == 'register':
            user_id = data.get('userId')
            if user_id:
                # If user already exists, just update the connection
                if user_id in connected_users:
                    logging.info(f"Updating connection for user '{user_id}'")
                
                connected_users[user_id] = websocket
                logging.info(f"User '{user_id}' registered and connected.")
                await websocket.send(json.dumps({"type": "register_ok"}))
            else:
                logging.warning(f"Registration failed - no user ID provided")
                await websocket.send(json.dumps({"type": "error", "message": "Invalid user ID"}))
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
                    data['senderUserId'] = user_id 
                    await target_ws.send(json.dumps(data))
                    logging.info(f"Forwarded message from '{user_id}' to '{target_user_id}': {data.get('type')}")
                else:
                    logging.warning(f"Target user '{target_user_id}' not found")
                    # Send user unavailable response
                    if data.get('type') == 'offer':
                        await websocket.send(json.dumps({
                            "type": "user_unavailable",
                            "targetUserId": target_user_id,
                            "message": "User is not online"
                        }))

            except json.JSONDecodeError:
                logging.error(f"Invalid JSON from {user_id}: {message}")
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

# HTTP health check handler for Render
async def health_check(request):
    """Simple health check endpoint for Render"""
    return web.Response(text='OK', status=200)

async def main():
    # Create HTTP server for health checks
    app = web.Application()
    app.router.add_get('/health', health_check)
    app.router.add_get('/', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Start HTTP server on PORT for health checks
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    logging.info(f"🏥 HTTP health check server started on port {PORT}")
    
    # Start WebSocket server on PORT + 1
    ws_port = PORT + 1
    async with websockets.serve(
        websocket_handler, 
        "0.0.0.0", 
        ws_port,
        # Render WebSocket config
        compression=None,
        ping_interval=20,
        ping_timeout=20,
        max_size=10 * 1024 * 1024  # 10MB max message size
    ):
        logging.info(f"🚀 WebSocket signaling server started on port {ws_port}")
        logging.info(f"📞 Ready to accept WebSocket connections on ws://0.0.0.0:{ws_port}")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())

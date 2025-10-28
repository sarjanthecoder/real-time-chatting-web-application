from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import jwt
import os
import json
from datetime import datetime, timedelta
from functools import wraps
import sqlite3
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'
app.config['UPLOAD_FOLDER'] = 'uploads/images'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=60, ping_interval=25)

# --- FIX: Moved home() function here and added the route ---
@app.route('/')
def home():
    return render_template('main.html')

# Create uploads folder if not exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database setup
def init_db():
    conn = sqlite3.connect('chat_app.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        username TEXT UNIQUE,
        profile_image TEXT,
        bio TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Messages table
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        chat_id TEXT NOT NULL,
        sender_id TEXT NOT NULL,
        receiver_id TEXT NOT NULL,
        text TEXT,
        image_url TEXT,
        timestamp BIGINT NOT NULL,
        status TEXT DEFAULT 'sent',
        deleted_for_sender BOOLEAN DEFAULT 0,
        deleted_for_receiver BOOLEAN DEFAULT 0,
        deleted_for_everyone BOOLEAN DEFAULT 0,
        FOREIGN KEY (sender_id) REFERENCES users(id),
        FOREIGN KEY (receiver_id) REFERENCES users(id)
    )''')
    
    # Chats table
    c.execute('''CREATE TABLE IF NOT EXISTS chats (
        user_id TEXT NOT NULL,
        chat_user_id TEXT NOT NULL,
        last_message TEXT,
        last_message_time BIGINT,
        PRIMARY KEY (user_id, chat_user_id),
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (chat_user_id) REFERENCES users(id)
    )''')
    
    # Online status table
    c.execute('''CREATE TABLE IF NOT EXISTS user_status (
        user_id TEXT PRIMARY KEY,
        online BOOLEAN DEFAULT 0,
        last_seen BIGINT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')
    
    conn.commit()
    conn.close()

init_db()

# Database helper functions
def get_db():
    conn = sqlite3.connect('chat_app.db')
    conn.row_factory = sqlite3.Row
    return conn

# JWT token decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user_id = data['user_id']
        except:
            return jsonify({'error': 'Token is invalid'}), 401
        
        return f(current_user_id, *args, **kwargs)
    
    return decorated

# Auth Routes
@app.route('/api/auth/signup', methods=['POST'])
def signup():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    # Check if user exists
    c.execute('SELECT * FROM users WHERE email = ?', (email,))
    if c.fetchone():
        conn.close()
        return jsonify({'error': 'User already exists'}), 400
    
    # Create user
    user_id = str(uuid.uuid4())
    hashed_password = generate_password_hash(password)
    
    c.execute('INSERT INTO users (id, email, password) VALUES (?, ?, ?)',
              (user_id, email, hashed_password))
    conn.commit()
    conn.close()
    
    # Generate token
    token = jwt.encode({
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(days=30)
    }, app.config['SECRET_KEY'])
    
    return jsonify({
        'token': token,
        'user_id': user_id,
        'email': email
    }), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute('SELECT * FROM users WHERE email = ?', (email,))
    user = c.fetchone()
    conn.close()
    
    if not user or not check_password_hash(user['password'], password):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Generate token
    token = jwt.encode({
        'user_id': user['id'],
        'exp': datetime.utcnow() + timedelta(days=30)
    }, app.config['SECRET_KEY'])
    
    return jsonify({
        'token': token,
        'user_id': user['id'],
        'email': user['email'],
        'username': user['username'],
        'profile_image': user['profile_image'],
        'bio': user['bio']
    }), 200

@app.route('/api/auth/profile', methods=['GET', 'POST'])
@token_required
def profile(current_user_id):
    conn = get_db()
    c = conn.cursor()
    
    if request.method == 'GET':
        c.execute('SELECT id, email, username, profile_image, bio FROM users WHERE id = ?', 
                  (current_user_id,))
        user = c.fetchone()
        conn.close()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify(dict(user)), 200
    
    elif request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        profile_image = data.get('profile_image', '👨‍💻')
        bio = data.get('bio', '')
        
        if not username:
            return jsonify({'error': 'Username required'}), 400
        
        # Check if username is unique
        c.execute('SELECT id FROM users WHERE username = ? AND id != ?', 
                  (username, current_user_id))
        if c.fetchone():
            conn.close()
            return jsonify({'error': 'Username already taken'}), 400
        
        # Update profile
        c.execute('''UPDATE users 
                     SET username = ?, profile_image = ?, bio = ? 
                     WHERE id = ?''',
                  (username, profile_image, bio, current_user_id))
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': 'Profile updated successfully',
            'username': username,
            'profile_image': profile_image,
            'bio': bio
        }), 200

# User Routes
@app.route('/api/users/search', methods=['GET'])
@token_required
def search_users(current_user_id):
    query = request.args.get('q', '').lower()
    
    if not query:
        return jsonify({'users': []}), 200
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''SELECT id, username, profile_image, bio 
                 FROM users 
                 WHERE username LIKE ? AND id != ? AND username IS NOT NULL
                 LIMIT 20''',
              (f'%{query}%', current_user_id))
    
    users = [dict(row) for row in c.fetchall()]
    
    # Get online status for each user
    for user in users:
        c.execute('SELECT online, last_seen FROM user_status WHERE user_id = ?', 
                  (user['id'],))
        status = c.fetchone()
        if status:
            user['online'] = bool(status['online'])
            user['last_seen'] = status['last_seen']
        else:
            user['online'] = False
            user['last_seen'] = int(datetime.now().timestamp() * 1000)
    
    conn.close()
    
    return jsonify({'users': users}), 200

@app.route('/api/users/<user_id>', methods=['GET'])
@token_required
def get_user(current_user_id, user_id):
    conn = get_db()
    c = conn.cursor()
    
    c.execute('SELECT id, username, profile_image, bio FROM users WHERE id = ?', 
              (user_id,))
    user = c.fetchone()
    
    if not user:
        conn.close()
        return jsonify({'error': 'User not found'}), 404
    
    user_data = dict(user)
    
    # Get status
    c.execute('SELECT online, last_seen FROM user_status WHERE user_id = ?', (user_id,))
    status = c.fetchone()
    if status:
        user_data['online'] = bool(status['online'])
        user_data['last_seen'] = status['last_seen']
    else:
        user_data['online'] = False
        user_data['last_seen'] = int(datetime.now().timestamp() * 1000)
    
    conn.close()
    
    return jsonify(user_data), 200

# Chat Routes
@app.route('/api/chats', methods=['GET'])
@token_required
def get_chats(current_user_id):
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''SELECT c.chat_user_id, c.last_message, c.last_message_time,
                     u.username, u.profile_image, u.bio,
                     s.online, s.last_seen
                 FROM chats c
                 JOIN users u ON c.chat_user_id = u.id
                 LEFT JOIN user_status s ON c.chat_user_id = s.user_id
                 WHERE c.user_id = ?
                 ORDER BY c.last_message_time DESC''',
              (current_user_id,))
    
    chats = []
    for row in c.fetchall():
        chat = dict(row)
        chat['online'] = bool(chat['online']) if chat['online'] is not None else False
        chats.append(chat)
    
    conn.close()
    
    return jsonify({'chats': chats}), 200

@app.route('/api/chats/create', methods=['POST'])
@token_required
def create_chat(current_user_id):
    data = request.get_json()
    chat_user_id = data.get('chat_user_id')
    
    if not chat_user_id:
        return jsonify({'error': 'chat_user_id required'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    # Check if chat already exists
    c.execute('SELECT * FROM chats WHERE user_id = ? AND chat_user_id = ?',
              (current_user_id, chat_user_id))
    
    if not c.fetchone():
        timestamp = int(datetime.now().timestamp() * 1000)
        
        # Create chat for both users
        c.execute('''INSERT INTO chats (user_id, chat_user_id, last_message, last_message_time)
                     VALUES (?, ?, ?, ?)''',
                  (current_user_id, chat_user_id, '', timestamp))
        
        c.execute('''INSERT INTO chats (user_id, chat_user_id, last_message, last_message_time)
                     VALUES (?, ?, ?, ?)''',
                  (chat_user_id, current_user_id, '', timestamp))
        
        conn.commit()
    
    conn.close()
    
    return jsonify({'message': 'Chat created successfully'}), 201

# Message Routes
@app.route('/api/messages/<chat_user_id>', methods=['GET'])
@token_required
def get_messages(current_user_id, chat_user_id):
    limit = int(request.args.get('limit', 50))
    
    conn = get_db()
    c = conn.cursor()
    
    chat_id = get_chat_id(current_user_id, chat_user_id)
    
    c.execute('''SELECT * FROM messages 
                 WHERE chat_id = ? 
                 AND deleted_for_everyone = 0
                 AND ((sender_id = ? AND deleted_for_sender = 0) 
                      OR (receiver_id = ? AND deleted_for_receiver = 0))
                 ORDER BY timestamp DESC
                 LIMIT ?''',
              (chat_id, current_user_id, current_user_id, limit))
    
    messages = [dict(row) for row in c.fetchall()]
    messages.reverse()
    
    conn.close()
    
    return jsonify({'messages': messages}), 200

@app.route('/api/messages/send', methods=['POST'])
@token_required
def send_message(current_user_id):
    data = request.get_json()
    receiver_id = data.get('receiver_id')
    text = data.get('text', '')
    image_url = data.get('image_url', '')
    
    if not receiver_id or (not text and not image_url):
        return jsonify({'error': 'receiver_id and message content required'}), 400
    
    conn = get_db()
    c = conn.cursor()
    
    message_id = str(uuid.uuid4())
    chat_id = get_chat_id(current_user_id, receiver_id)
    timestamp = int(datetime.now().timestamp() * 1000)
    
    # Insert message
    c.execute('''INSERT INTO messages 
                 (id, chat_id, sender_id, receiver_id, text, image_url, timestamp, status)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (message_id, chat_id, current_user_id, receiver_id, text, image_url, timestamp, 'sent'))
    
    # Update last message in chats
    last_msg = text if text else '📷 Image'
    c.execute('''INSERT OR REPLACE INTO chats (user_id, chat_user_id, last_message, last_message_time)
                 VALUES (?, ?, ?, ?)''',
              (current_user_id, receiver_id, last_msg, timestamp))
    
    c.execute('''INSERT OR REPLACE INTO chats (user_id, chat_user_id, last_message, last_message_time)
                 VALUES (?, ?, ?, ?)''',
              (receiver_id, current_user_id, last_msg, timestamp))
    
    conn.commit()
    conn.close()
    
    message = {
        'id': message_id,
        'chat_id': chat_id,
        'sender_id': current_user_id,
        'receiver_id': receiver_id,
        'text': text,
        'image_url': image_url,
        'timestamp': timestamp,
        'status': 'sent'
    }
    
    # Emit via WebSocket
    socketio.emit('new_message', message, room=receiver_id)
    socketio.emit('new_message', message, room=current_user_id)
    
    return jsonify(message), 201

@app.route('/api/messages/<message_id>/delete', methods=['POST'])
@token_required
def delete_message(current_user_id, message_id):
    data = request.get_json()
    delete_type = data.get('type', 'me')  # 'me' or 'everyone'
    
    conn = get_db()
    c = conn.cursor()
    
    # Get message
    c.execute('SELECT * FROM messages WHERE id = ?', (message_id,))
    message = c.fetchone()
    
    if not message:
        conn.close()
        return jsonify({'error': 'Message not found'}), 404
    
    if delete_type == 'everyone' and message['sender_id'] != current_user_id:
        conn.close()
        return jsonify({'error': 'You can only delete your own messages for everyone'}), 403
    
    if delete_type == 'everyone':
        c.execute('UPDATE messages SET deleted_for_everyone = 1 WHERE id = ?', (message_id,))
        socketio.emit('message_deleted', {'message_id': message_id, 'type': 'everyone'}, 
                      room=message['receiver_id'])
    else:
        if message['sender_id'] == current_user_id:
            c.execute('UPDATE messages SET deleted_for_sender = 1 WHERE id = ?', (message_id,))
        else:
            c.execute('UPDATE messages SET deleted_for_receiver = 1 WHERE id = ?', (message_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Message deleted successfully'}), 200

# Image upload
@app.route('/api/upload/image', methods=['POST'])
@token_required
def upload_image(current_user_id):
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400
    
    file = request.files['image']
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file:
        filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        image_url = f"/api/images/{filename}"
        
        return jsonify({'image_url': image_url}), 200

@app.route('/api/images/<filename>')
def get_image(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# WebSocket events
@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('authenticate')
def handle_authenticate(data):
    token = data.get('token')
    
    try:
        if token.startswith('Bearer '):
            token = token[7:]
        user_data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        user_id = user_data['user_id']
        
        # Join user's personal room
        join_room(user_id)
        
        # Update online status
        conn = get_db()
        c = conn.cursor()
        timestamp = int(datetime.now().timestamp() * 1000)
        
        c.execute('''INSERT OR REPLACE INTO user_status (user_id, online, last_seen)
                     VALUES (?, ?, ?)''',
                  (user_id, 1, timestamp))
        conn.commit()
        conn.close()
        
        # Notify others
        socketio.emit('user_online', {'user_id': user_id, 'online': True}, broadcast=True)
        
        emit('authenticated', {'user_id': user_id})
    except:
        emit('auth_error', {'error': 'Invalid token'})

@socketio.on('user_offline')
def handle_user_offline(data):
    user_id = data.get('user_id')
    
    if user_id:
        conn = get_db()
        c = conn.cursor()
        timestamp = int(datetime.now().timestamp() * 1000)
        
        c.execute('''UPDATE user_status 
                     SET online = 0, last_seen = ?
                     WHERE user_id = ?''',
                  (timestamp, user_id))
        conn.commit()
        conn.close()
        
        leave_room(user_id)
        socketio.emit('user_offline', {'user_id': user_id, 'last_seen': timestamp}, broadcast=True)

@socketio.on('typing')
def handle_typing(data):
    receiver_id = data.get('receiver_id')
    sender_id = data.get('sender_id')
    is_typing = data.get('typing', False)
    
    socketio.emit('user_typing', {
        'user_id': sender_id,
        'typing': is_typing
    }, room=receiver_id)

@socketio.on('message_read')
def handle_message_read(data):
    message_id = data.get('message_id')
    reader_id = data.get('reader_id')
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute('UPDATE messages SET status = ? WHERE id = ?', ('read', message_id))
    c.execute('SELECT sender_id FROM messages WHERE id = ?', (message_id,))
    result = c.fetchone()
    
    if result:
        sender_id = result['sender_id']
        socketio.emit('message_status', {
            'message_id': message_id,
            'status': 'read'
        }, room=sender_id)
    
    conn.commit()
    conn.close()

# Helper function
def get_chat_id(uid1, uid2):
    return f"{min(uid1, uid2)}_{max(uid1, uid2)}"

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
from flask import Flask, request, jsonify, send_from_directory, redirect
from flask_cors import CORS
import sqlite3
import json
from datetime import datetime
import os
import uuid
import base64
from werkzeug.utils import secure_filename
import qrcode
from io import BytesIO
import re

app = Flask(__name__, static_folder='.')
CORS(app)

# Configuration
DATABASE = 'kc_jain_advocate.db'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi'}
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Create upload folders if not exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'images'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'videos'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'qrcodes'), exist_ok=True)

# ==================== DATABASE INITIALIZATION ====================
def init_db():
    """Initialize SQLite database with all required tables"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Content table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS content (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            text TEXT,
            category TEXT,
            image_url TEXT,
            video_url TEXT,
            created_date TIMESTAMP,
            status TEXT DEFAULT 'Active',
            media_type TEXT,
            file_count INTEGER DEFAULT 0,
            style TEXT DEFAULT 'default',
            priority INTEGER DEFAULT 0
        )
    ''')
    
    # QR Data table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS qr_data (
            id TEXT PRIMARY KEY,
            tree_id TEXT NOT NULL,
            tree_name TEXT NOT NULL,
            scientific_name TEXT,
            planted_date TEXT,
            location TEXT,
            coordinates TEXT,
            planted_by TEXT,
            maintenance_by TEXT,
            tree_age TEXT,
            tree_height TEXT,
            description TEXT,
            health_status TEXT DEFAULT 'Good',
            last_maintenance TEXT,
            next_maintenance TEXT,
            watering_schedule TEXT,
            qr_code_url TEXT,
            tree_image_url TEXT,
            tree_video_url TEXT,
            created_date TIMESTAMP,
            status TEXT DEFAULT 'Active',
            qr_style TEXT DEFAULT 'default'
        )
    ''')
    
    # Profile config table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS profile_config (
            key TEXT PRIMARY KEY,
            value TEXT,
            thumbnail TEXT,
            updated_at TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database on startup
init_db()

# ==================== HELPER FUNCTIONS ====================
def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_base64_file(base64_data, filename, subfolder=''):
    """Save base64 encoded file to disk and return URL"""
    try:
        # Extract base64 content
        if ',' in base64_data:
            base64_data = base64_data.split(',')[1]
        
        # Decode and save
        file_data = base64.b64decode(base64_data)
        
        # Create unique filename
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'bin'
        unique_name = f"{uuid.uuid4().hex}.{ext}"
        
        # Determine subfolder based on file type
        if ext in ['jpg', 'jpeg', 'png', 'gif']:
            save_path = os.path.join('images', unique_name)
        elif ext in ['mp4', 'mov', 'avi']:
            save_path = os.path.join('videos', unique_name)
        elif ext == 'png' and 'qr' in filename.lower():
            save_path = os.path.join('qrcodes', unique_name)
        else:
            save_path = unique_name
            
        full_path = os.path.join(app.config['UPLOAD_FOLDER'], save_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, 'wb') as f:
            f.write(file_data)
        
        # Return URL that can be accessed via /uploads/
        return f'/uploads/{save_path}'
    except Exception as e:
        print(f"Error saving file: {e}")
        return None

def format_date(date_str):
    """Format date for display"""
    try:
        if not date_str:
            return 'Recent'
        
        date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        now = datetime.now()
        diff = (now - date).days
        
        if diff == 0:
            return 'Today'
        elif diff == 1:
            return 'Yesterday'
        elif diff < 7:
            return f'{diff} days ago'
        elif diff < 30:
            weeks = diff // 7
            return f'{weeks} week{"s" if weeks > 1 else ""} ago'
        else:
            return date.strftime('%d %b %Y')
    except:
        return 'Recent'

def get_embeddable_url(url):
    """Convert various URL types to embeddable format"""
    if not url:
        return ''
    
    # Already our upload URL
    if url.startswith('/uploads/'):
        return url
    
    # Google Drive
    if 'drive.google.com' in url:
        file_id_match = re.search(r'/d/([a-zA-Z0-9_-]+)', url) or \
                       re.search(r'id=([a-zA-Z0-9_-]+)', url)
        if file_id_match:
            file_id = file_id_match.group(1)
            return f'/api/drive-proxy/{file_id}'
    
    # YouTube
    if 'youtube.com' in url or 'youtu.be' in url:
        video_id_match = re.search(r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]+)', url)
        if video_id_match:
            video_id = video_id_match.group(1)
            return f'https://www.youtube.com/embed/{video_id}'
    
    return url

# ==================== API ENDPOINTS ====================

@app.route('/')
def serve_frontend():
    """Serve the main HTML file"""
    return send_from_directory('.', 'index.html')

@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    """Serve uploaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/drive-proxy/<file_id>')
def drive_proxy(file_id):
    """Proxy for Google Drive files"""
    return redirect(f'https://drive.google.com/uc?export=download&id={file_id}')

# ============ CONTENT ENDPOINTS ============
@app.route('/api/content', methods=['GET'])
def get_all_content():
    """Get all content"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM content 
        WHERE status = 'Active' 
        ORDER BY created_date DESC
    ''')
    
    rows = cursor.fetchall()
    content = []
    
    for row in rows:
        item = dict(row)
        item['displayDate'] = format_date(item['created_date'])
        item['date'] = item['created_date']
        
        # Build media array
        media = []
        if item['image_url']:
            media.append({
                'type': 'image',
                'url': get_embeddable_url(item['image_url']),
                'thumbnail': get_embeddable_url(item['image_url'])
            })
        if item['video_url']:
            media.append({
                'type': 'video',
                'url': get_embeddable_url(item['video_url']),
                'thumbnail': None
            })
        item['media'] = media
        content.append(item)
    
    conn.close()
    return jsonify(content)

@app.route('/api/content', methods=['POST'])
def save_content():
    """Save new content"""
    try:
        data = request.json
        content_data = data.get('data', {})
        files = data.get('files', [])
        
        content_id = content_data.get('id') or f"{content_data.get('type', 'post')}-{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()
        
        image_url = content_data.get('imageUrl', '')
        video_url = content_data.get('videoUrl', '')
        media_type = ''
        file_count = 0
        
        # Process uploaded files
        for file_data in files:
            filename = file_data.get('name', f"file_{uuid.uuid4().hex}")
            file_type = file_data.get('type', '')
            base64_data = file_data.get('data', '')
            
            saved_url = save_base64_file(base64_data, filename)
            if saved_url:
                if 'image' in file_type:
                    image_url = saved_url
                    media_type = 'image'
                elif 'video' in file_type:
                    video_url = saved_url
                    media_type = 'video' if not media_type else 'mixed'
                file_count += 1
        
        # Save to database
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO content 
            (id, type, title, text, category, image_url, video_url, created_date, 
             status, media_type, file_count, style, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            content_id,
            content_data.get('type', 'post'),
            content_data.get('title', ''),
            content_data.get('text', ''),
            content_data.get('category', 'General'),
            image_url,
            video_url,
            now,
            'Active',
            media_type,
            file_count,
            content_data.get('style', 'default'),
            content_data.get('priority', 0)
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Content saved successfully',
            'contentId': content_id,
            'imageUrl': get_embeddable_url(image_url),
            'videoUrl': get_embeddable_url(video_url),
            'timestamp': now,
            'displayDate': format_date(now)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/content/<content_id>', methods=['DELETE'])
def delete_content(content_id):
    """Delete content (soft delete)"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('UPDATE content SET status = "Inactive" WHERE id = ?', (content_id,))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Content deleted successfully',
            'contentId': content_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ QR CODE ENDPOINTS ============
@app.route('/api/qr', methods=['GET'])
def get_all_qr():
    """Get all QR data"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM qr_data 
        WHERE status = 'Active' 
        ORDER BY created_date DESC
    ''')
    
    rows = cursor.fetchall()
    qr_list = []
    
    for row in rows:
        item = dict(row)
        item['displayPlantedDate'] = format_date(item['planted_date'])
        item['displayCreatedDate'] = format_date(item['created_date'])
        item['displayLastMaintenance'] = format_date(item['last_maintenance'])
        item['displayNextMaintenance'] = format_date(item['next_maintenance'])
        item['plantedDate'] = item['planted_date']
        item['createdDate'] = item['created_date']
        qr_list.append(item)
    
    conn.close()
    return jsonify(qr_list)

@app.route('/api/qr', methods=['POST'])
def generate_qr():
    """Generate QR code for tree"""
    try:
        data = request.json
        qr_data = data.get('data', {})
        files = data.get('files', [])
        
        qr_id = f"TREE-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now().isoformat()
        
        tree_image_url = ''
        tree_video_url = ''
        
        # Process uploaded files
        for file_data in files:
            filename = file_data.get('name', f"tree_{uuid.uuid4().hex}")
            file_type = file_data.get('type', '')
            base64_data = file_data.get('data', '')
            
            saved_url = save_base64_file(base64_data, filename)
            if saved_url:
                if 'image' in file_type:
                    tree_image_url = saved_url
                elif 'video' in file_type:
                    tree_video_url = saved_url
        
        # Prepare QR data
        qr_text_data = {
            'id': qr_id,
            'treeId': qr_data.get('treeId', ''),
            'treeName': qr_data.get('treeName', ''),
            'scientificName': qr_data.get('scientificName', ''),
            'plantedDate': format_date(qr_data.get('plantedDate', now)),
            'location': qr_data.get('location', ''),
            'coordinates': qr_data.get('coordinates', ''),
            'plantedBy': qr_data.get('plantedBy', ''),
            'maintenanceBy': qr_data.get('maintenanceBy', ''),
            'treeAge': qr_data.get('treeAge', ''),
            'treeHeight': qr_data.get('treeHeight', ''),
            'description': qr_data.get('description', ''),
            'healthStatus': qr_data.get('healthStatus', 'Good'),
            'lastMaintenance': format_date(qr_data.get('lastMaintenance', '')),
            'nextMaintenance': format_date(qr_data.get('nextMaintenance', '')),
            'wateringSchedule': qr_data.get('wateringSchedule', ''),
            'generated': format_date(now)
        }
        
        # Generate QR code image
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(json.dumps(qr_text_data))
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Save QR code
        qr_filename = f"qr_{qr_id}.png"
        qr_path = os.path.join(app.config['UPLOAD_FOLDER'], 'qrcodes', qr_filename)
        os.makedirs(os.path.dirname(qr_path), exist_ok=True)
        qr_img.save(qr_path)
        
        qr_code_url = f'/uploads/qrcodes/{qr_filename}'
        
        # Save to database
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO qr_data 
            (id, tree_id, tree_name, scientific_name, planted_date, location,
             coordinates, planted_by, maintenance_by, tree_age, tree_height,
             description, health_status, last_maintenance, next_maintenance,
             watering_schedule, qr_code_url, tree_image_url, tree_video_url,
             created_date, status, qr_style)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            qr_id,
            qr_data.get('treeId', ''),
            qr_data.get('treeName', ''),
            qr_data.get('scientificName', ''),
            qr_data.get('plantedDate', now),
            qr_data.get('location', ''),
            qr_data.get('coordinates', ''),
            qr_data.get('plantedBy', ''),
            qr_data.get('maintenanceBy', ''),
            qr_data.get('treeAge', ''),
            qr_data.get('treeHeight', ''),
            qr_data.get('description', ''),
            qr_data.get('healthStatus', 'Good'),
            qr_data.get('lastMaintenance', ''),
            qr_data.get('nextMaintenance', ''),
            qr_data.get('wateringSchedule', ''),
            qr_code_url,
            tree_image_url,
            tree_video_url,
            now,
            'Active',
            qr_data.get('qrStyle', 'default')
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Tree QR data saved successfully',
            'qrId': qr_id,
            'qrCodeUrl': qr_code_url,
            'treeImageUrl': tree_image_url,
            'treeVideoUrl': tree_video_url,
            'qrData': qr_text_data,
            'displayPlantedDate': format_date(qr_data.get('plantedDate', now)),
            'displayCreatedDate': format_date(now),
            'timestamp': now
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/qr/<qr_id>', methods=['DELETE'])
def delete_qr(qr_id):
    """Delete QR data (soft delete)"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('UPDATE qr_data SET status = "Inactive" WHERE id = ?', (qr_id,))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'QR data deleted successfully',
            'qrId': qr_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ PROFILE ENDPOINTS ============
@app.route('/api/profile', methods=['GET'])
def get_profile():
    """Get profile configuration"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM profile_config WHERE key = "profile-image"')
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return jsonify({
            'profileImage': row['value'],
            'thumbnailUrl': row['thumbnail'] or row['value'],
            'updatedAt': row['updated_at']
        })
    else:
        return jsonify({
            'profileImage': '',
            'thumbnailUrl': '',
            'updatedAt': None
        })

@app.route('/api/profile', methods=['POST'])
def update_profile():
    """Update profile image"""
    try:
        data = request.json
        image_data = data.get('imageData', '')
        filename = data.get('fileName', 'profile.jpg')
        
        # Save file
        saved_url = save_base64_file(image_data, filename)
        
        if saved_url:
            now = datetime.now().isoformat()
            
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO profile_config (key, value, thumbnail, updated_at)
                VALUES (?, ?, ?, ?)
            ''', ('profile-image', saved_url, saved_url, now))
            
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'profileImage': saved_url,
                'thumbnailUrl': saved_url,
                'message': 'Profile image updated successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to save file'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ STATISTICS ENDPOINT ============
@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get website statistics"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM content WHERE type = 'case' AND status = 'Active'")
    cases = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM content WHERE type = 'post' AND status = 'Active'")
    posts = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM content WHERE type = 'blog' AND status = 'Active'")
    blogs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM content WHERE type = 'announcement' AND status = 'Active'")
    announcements = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM qr_data WHERE status = 'Active'")
    qr_codes = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'cases': cases,
        'posts': posts,
        'blogs': blogs,
        'announcements': announcements,
        'qr': qr_codes,
        'totalContent': cases + posts + blogs + announcements,
        'updated': datetime.now().isoformat()
    })

# ============ PING ENDPOINT ============
@app.route('/api/ping', methods=['GET'])
def ping():
    """Health check endpoint"""
    return jsonify({
        'status': 'OK',
        'message': 'KC Jain Advocate Website API',
        'version': '4.1.0-python',
        'timestamp': datetime.now().isoformat(),
        'displayDate': format_date(datetime.now().isoformat()),
        'timezone': 'Asia/Kolkata',
        'features': ['File Upload', 'QR Generation', 'Statistics', 'Profile Management', 'SQLite Database']
    })

# ============ MAIN ============
if __name__ == '__main__':
    print("=" * 50)
    print("KC Jain Advocate Website - Python Backend")
    print("=" * 50)
    print(f"Database: {DATABASE}")
    print(f"Upload folder: {UPLOAD_FOLDER}")
    print("=" * 50)
    print("Starting server at http://localhost:5000")
    print("Press Ctrl+C to stop")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
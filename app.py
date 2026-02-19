from flask import Flask, request, jsonify, send_from_directory, redirect, url_for, send_file
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
import hashlib
from PIL import Image, ImageDraw, ImageFont
import mimetypes
import shutil
import logging
from logging.handlers import RotatingFileHandler
import time
import traceback

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Configuration
DATABASE = 'kc_jain_advocate.db'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'mov', 'avi', 'pdf', 'doc', 'docx'}
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max file size
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB max image size
MAX_VIDEO_SIZE = 100 * 1024 * 1024  # 100MB max video size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['MAX_IMAGE_SIZE'] = MAX_IMAGE_SIZE
app.config['MAX_VIDEO_SIZE'] = MAX_VIDEO_SIZE
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Disable caching for development
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

# Create upload folders if not exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'images'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'videos'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'qrcodes'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'documents'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'thumbnails'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'profile'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'temp'), exist_ok=True)

# Setup logging
log_handler = RotatingFileHandler('app.log', maxBytes=10485760, backupCount=10)
log_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
log_handler.setLevel(logging.INFO)
app.logger.addHandler(log_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('KC Jain Advocate Website startup')

# ==================== DATABASE INITIALIZATION ====================
def init_db():
    """Initialize SQLite database with all required tables"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Content table with improved schema
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS content (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                text TEXT,
                category TEXT,
                image_urls TEXT,  -- Store multiple image URLs as JSON
                video_url TEXT,
                created_date TIMESTAMP,
                updated_date TIMESTAMP,
                status TEXT DEFAULT 'Active',
                media_type TEXT,
                file_count INTEGER DEFAULT 0,
                style TEXT DEFAULT 'default',
                priority INTEGER DEFAULT 0,
                tags TEXT,
                views INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                shares INTEGER DEFAULT 0,
                author TEXT DEFAULT 'KC Jain',
                featured BOOLEAN DEFAULT 0,
                language TEXT DEFAULT 'en',
                seo_title TEXT,
                seo_description TEXT,
                seo_keywords TEXT
            )
        ''')
        
        # QR Data table with improved schema
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
                tree_image_urls TEXT,  -- Store multiple image URLs as JSON
                tree_video_url TEXT,
                created_date TIMESTAMP,
                updated_date TIMESTAMP,
                status TEXT DEFAULT 'Active',
                qr_style TEXT DEFAULT 'default',
                qr_scan_count INTEGER DEFAULT 0,
                qr_download_count INTEGER DEFAULT 0,
                qr_print_count INTEGER DEFAULT 0,
                tree_age_years INTEGER,
                tree_age_months INTEGER,
                girth_size TEXT,
                canopy_size TEXT,
                soil_type TEXT,
                watering_frequency TEXT,
                fertilizer_schedule TEXT,
                pest_control TEXT,
                special_notes TEXT
            )
        ''')
        
        # Profile config table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profile_config (
                key TEXT PRIMARY KEY,
                value TEXT,
                thumbnail TEXT,
                updated_at TIMESTAMP,
                metadata TEXT,
                version INTEGER DEFAULT 1,
                created_at TIMESTAMP
            )
        ''')
        
        # Admin users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT,
                role TEXT DEFAULT 'admin',
                created_date TIMESTAMP,
                last_login TIMESTAMP,
                last_ip TEXT,
                login_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'Active',
                profile_picture TEXT,
                permissions TEXT,
                two_factor_enabled BOOLEAN DEFAULT 0,
                two_factor_secret TEXT
            )
        ''')
        
        # Settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP,
                description TEXT,
                type TEXT DEFAULT 'string',
                group_name TEXT DEFAULT 'general'
            )
        ''')
        
        # Sessions table for managing user sessions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                token TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TIMESTAMP,
                expires_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES admin_users (id)
            )
        ''')
        
        # Activity log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                entity_type TEXT,
                entity_id TEXT,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES admin_users (id)
            )
        ''')
        
        conn.commit()
        
        # Check and add missing columns to existing tables
        try:
            # Check if created_at exists in settings table
            cursor.execute("PRAGMA table_info(settings)")
            columns = [column[1] for column in cursor.fetchall()]
            
            # Add missing columns if needed
            if 'created_at' not in columns:
                cursor.execute("ALTER TABLE settings ADD COLUMN created_at TIMESTAMP")
                app.logger.info("Added created_at column to settings table")
            
            # Add group_name if missing
            if 'group_name' not in columns:
                cursor.execute("ALTER TABLE settings ADD COLUMN group_name TEXT DEFAULT 'general'")
                app.logger.info("Added group_name column to settings table")
            
            # Add type if missing
            if 'type' not in columns:
                cursor.execute("ALTER TABLE settings ADD COLUMN type TEXT DEFAULT 'string'")
                app.logger.info("Added type column to settings table")
            
            # Add description if missing
            if 'description' not in columns:
                cursor.execute("ALTER TABLE settings ADD COLUMN description TEXT")
                app.logger.info("Added description column to settings table")
                
        except Exception as e:
            app.logger.warning(f"Error altering settings table: {e}")
        
        conn.commit()
        
        # Insert default admin user if not exists (password: admin123)
        cursor.execute("SELECT * FROM admin_users WHERE email = 'kcjain@gmail.com'")
        if not cursor.fetchone():
            password_hash = hashlib.sha256('admin123'.encode()).hexdigest()
            cursor.execute('''
                INSERT INTO admin_users (email, password_hash, name, role, created_date, status, permissions)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                'kcjain@gmail.com', 
                password_hash, 
                'KC Jain', 
                'super_admin', 
                datetime.now().isoformat(), 
                'Active',
                json.dumps(['all'])
            ))
            app.logger.info("Default admin user created")
        
        cursor.execute("SELECT * FROM admin_users WHERE email = 'shivamsharmaanna@gmail.com'")
        if not cursor.fetchone():
            password_hash = hashlib.sha256('admin123'.encode()).hexdigest()
            cursor.execute('''
                INSERT INTO admin_users (email, password_hash, name, role, created_date, status, permissions)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                'shivamsharmaanna@gmail.com', 
                password_hash, 
                'Shivam Sharma', 
                'admin', 
                datetime.now().isoformat(), 
                'Active',
                json.dumps(['content', 'qr', 'profile'])
            ))
            app.logger.info("Second admin user created")
        
        # Check if default profile image exists
        cursor.execute("SELECT * FROM profile_config WHERE key = 'profile-image'")
        if not cursor.fetchone():
            # Create a default profile image placeholder
            default_profile_path = os.path.join(UPLOAD_FOLDER, 'profile', 'default-profile.jpg')
            os.makedirs(os.path.dirname(default_profile_path), exist_ok=True)
            
            # Create a simple default profile image if it doesn't exist
            if not os.path.exists(default_profile_path):
                try:
                    # Create a simple colored placeholder image
                    img = Image.new('RGB', (400, 400), color='#0a1929')
                    draw = ImageDraw.Draw(img)
                    
                    # Try to use a font, fallback to default if not available
                    try:
                        font = ImageFont.truetype("arial.ttf", 48)
                    except:
                        font = ImageFont.load_default()
                    
                    # Draw text
                    draw.text((200, 150), "KC", fill='#c9a959', anchor='mm', font=font)
                    draw.text((200, 220), "JAIN", fill='#c9a959', anchor='mm', font=font)
                    draw.text((200, 300), "Supreme Court", fill='#ffffff', anchor='mm', font=ImageFont.load_default())
                    
                    img.save(default_profile_path, quality=95)
                    app.logger.info("Default profile image created successfully")
                except Exception as e:
                    app.logger.error(f"Error creating default profile image: {e}")
            
            cursor.execute('''
                INSERT INTO profile_config (key, value, thumbnail, updated_at, metadata, created_at, version)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                'profile-image',
                '/uploads/profile/default-profile.jpg',
                '/uploads/profile/default-profile.jpg',
                datetime.now().isoformat(),
                json.dumps({'name': 'Default Profile', 'type': 'default', 'created': True}),
                datetime.now().isoformat(),
                1
            ))
        
        # Insert default settings
        default_settings = [
            ('site_title', 'KC Jain - Supreme Court Advocate', 'Website title', 'string', 'general'),
            ('site_description', 'Distinguished Supreme Court practice with a legacy of landmark judgments', 'Website description', 'string', 'general'),
            ('contact_email', 'kcjain@gmail.com', 'Primary contact email', 'string', 'contact'),
            ('contact_phone', '+91 94122 63072', 'Contact phone number', 'string', 'contact'),
            ('address', 'Room No. 7, Supreme Court Complex, New Delhi - 110001', 'Office address', 'text', 'contact'),
            ('working_hours', 'Mon - Sat: 10:00 AM - 6:00 PM', 'Working hours', 'string', 'general'),
            ('enable_qr_system', 'true', 'Enable QR code system', 'boolean', 'features'),
            ('enable_comments', 'false', 'Enable comments on content', 'boolean', 'features'),
            ('maintenance_mode', 'false', 'Maintenance mode status', 'boolean', 'system'),
            ('analytics_id', '', 'Google Analytics ID', 'string', 'analytics'),
            ('facebook_url', '#', 'Facebook page URL', 'string', 'social'),
            ('twitter_url', '#', 'Twitter profile URL', 'string', 'social'),
            ('linkedin_url', '#', 'LinkedIn profile URL', 'string', 'social'),
            ('instagram_url', '#', 'Instagram profile URL', 'string', 'social')
        ]
        
        now = datetime.now().isoformat()
        for key, value, description, type_val, group in default_settings:
            cursor.execute("SELECT * FROM settings WHERE key = ?", (key,))
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO settings (key, value, updated_at, description, type, group_name)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (key, value, now, description, type_val, group))
        
        conn.commit()
        conn.close()
        app.logger.info("Database initialized successfully")
        
    except Exception as e:
        app.logger.error(f"Database initialization error: {e}")
        app.logger.error(traceback.format_exc())

# Initialize database on startup
init_db()

# ==================== HELPER FUNCTIONS ====================
def allowed_file(filename):
    """Check if file extension is allowed"""
    if '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS

def get_file_type(filename):
    """Determine file type based on extension"""
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg']:
        return 'image'
    elif ext in ['mp4', 'mov', 'avi', 'mkv', 'webm', 'flv', 'wmv']:
        return 'video'
    elif ext in ['pdf']:
        return 'pdf'
    elif ext in ['doc', 'docx', 'txt', 'rtf', 'odt']:
        return 'document'
    elif ext in ['mp3', 'wav', 'ogg', 'flac']:
        return 'audio'
    else:
        return 'other'

def create_thumbnail(image_path, thumbnail_path, size=(300, 300)):
    """Create thumbnail for image"""
    try:
        if os.path.exists(image_path):
            img = Image.open(image_path)
            
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'LA', 'P'):
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = rgb_img
            
            img.thumbnail(size, Image.Resampling.LANCZOS)
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
            
            img.save(thumbnail_path, optimize=True, quality=85)
            app.logger.info(f"Thumbnail created: {thumbnail_path}")
            return True
    except Exception as e:
        app.logger.error(f"Error creating thumbnail: {e}")
    return False

def save_base64_file(base64_data, filename, subfolder=''):
    """Save base64 encoded file to disk and return URL"""
    temp_path = None
    try:
        # Extract base64 content
        if ',' in base64_data:
            base64_data = base64_data.split(',')[1]
        
        # Decode and save
        file_data = base64.b64decode(base64_data)
        
        # Check file size
        file_size = len(file_data)
        file_type = get_file_type(filename)
        
        if file_type == 'image' and file_size > app.config['MAX_IMAGE_SIZE']:
            raise Exception(f"Image size exceeds {app.config['MAX_IMAGE_SIZE'] // (1024*1024)}MB limit")
        elif file_type == 'video' and file_size > app.config['MAX_VIDEO_SIZE']:
            raise Exception(f"Video size exceeds {app.config['MAX_VIDEO_SIZE'] // (1024*1024)}MB limit")
        
        # Create unique filename
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'bin'
        unique_name = f"{uuid.uuid4().hex}.{ext}"
        
        # Determine subfolder based on file type and purpose
        if 'profile' in filename.lower() or subfolder == 'profile':
            save_path = os.path.join('profile', unique_name)
        elif file_type == 'image':
            save_path = os.path.join('images', unique_name)
        elif file_type == 'video':
            save_path = os.path.join('videos', unique_name)
        elif ext == 'png' and 'qr' in filename.lower():
            save_path = os.path.join('qrcodes', unique_name)
        elif file_type == 'pdf':
            save_path = os.path.join('documents', unique_name)
        else:
            save_path = os.path.join('others', unique_name)
        
        # Save file
        full_path = os.path.join(app.config['UPLOAD_FOLDER'], save_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        # Save to temp first to verify
        temp_path = full_path + '.tmp'
        with open(temp_path, 'wb') as f:
            f.write(file_data)
        
        # Verify file integrity (for images)
        if file_type == 'image':
            try:
                img = Image.open(temp_path)
                img.verify()
                # Reopen after verify (verify closes the file)
                img = Image.open(temp_path)
                
                # Optimize image
                if img.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                
                # Resize if too large (max 1920px on longest side)
                max_size = 1920
                if max(img.size) > max_size:
                    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                
                # Save optimized image
                img.save(full_path, optimize=True, quality=90)
                
                # Create thumbnail
                thumbnail_path = os.path.join('thumbnails', f"thumb_{unique_name}")
                full_thumbnail_path = os.path.join(app.config['UPLOAD_FOLDER'], thumbnail_path)
                create_thumbnail(full_path, full_thumbnail_path)
                
                # Remove temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                
                return {
                    'url': f'/uploads/{save_path}',
                    'thumbnail': f'/uploads/{thumbnail_path}',
                    'type': 'image',
                    'size': os.path.getsize(full_path),
                    'originalSize': file_size,
                    'dimensions': img.size
                }
            except Exception as e:
                app.logger.error(f"Image verification failed: {e}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise Exception(f"Invalid image file: {e}")
        else:
            # For non-image files, just move from temp
            shutil.move(temp_path, full_path)
            
            return {
                'url': f'/uploads/{save_path}',
                'type': file_type,
                'size': file_size
            }
            
    except Exception as e:
        app.logger.error(f"Error saving file: {e}")
        # Clean up temp file if it exists
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        return None

def format_date(date_str):
    """Format date for display"""
    try:
        if not date_str:
            return 'Recent'
        
        # Handle different date formats
        if isinstance(date_str, str):
            # Try to parse ISO format
            try:
                date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            except:
                # Try other common formats
                try:
                    date = datetime.strptime(date_str, '%Y-%m-%d')
                except:
                    try:
                        date = datetime.strptime(date_str, '%d/%m/%Y')
                    except:
                        try:
                            date = datetime.strptime(date_str, '%d-%m-%Y')
                        except:
                            return date_str
        else:
            date = date_str
        
        now = datetime.now()
        diff = (now - date).days
        
        if diff < 0:
            return date.strftime('%d %b %Y')
        elif diff == 0:
            return 'Today'
        elif diff == 1:
            return 'Yesterday'
        elif diff < 7:
            return f'{diff} days ago'
        elif diff < 30:
            weeks = diff // 7
            return f'{weeks} week{"s" if weeks > 1 else ""} ago'
        elif diff < 365:
            months = diff // 30
            return f'{months} month{"s" if months > 1 else ""} ago'
        else:
            return date.strftime('%d %b %Y')
    except Exception as e:
        app.logger.error(f"Date formatting error: {e}")
        return 'Recent'

def get_embeddable_url(url):
    """Convert various URL types to embeddable format"""
    if not url or not isinstance(url, str):
        return url
    
    # Already our upload URL
    if url.startswith('/uploads/'):
        return url
    
    # Google Drive
    if 'drive.google.com' in url:
        file_id_match = re.search(r'/d/([a-zA-Z0-9_-]+)', url) or \
                       re.search(r'id=([a-zA-Z0-9_-]+)', url) or \
                       re.search(r'file/d/([a-zA-Z0-9_-]+)', url)
        if file_id_match:
            file_id = file_id_match.group(1)
            return f'https://drive.google.com/file/d/{file_id}/preview'
    
    # YouTube
    if 'youtube.com' in url or 'youtu.be' in url:
        video_id_match = re.search(r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]+)', url)
        if video_id_match:
            video_id = video_id_match.group(1)
            return f'https://www.youtube.com/embed/{video_id}'
    
    # Vimeo
    if 'vimeo.com' in url:
        video_id_match = re.search(r'vimeo\.com/(\d+)', url) or \
                        re.search(r'player\.vimeo\.com/video/(\d+)', url)
        if video_id_match:
            video_id = video_id_match.group(1)
            return f'https://player.vimeo.com/video/{video_id}'
    
    # Facebook
    if 'facebook.com' in url:
        return url.replace('watch?v=', 'embed/')
    
    return url

def verify_admin(email, password):
    """Verify admin credentials"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        cursor.execute('''
            SELECT * FROM admin_users 
            WHERE email = ? AND password_hash = ? AND status = 'Active'
        ''', (email, password_hash))
        
        user = cursor.fetchone()
        conn.close()
        
        if user:
            # Update last login
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE admin_users SET last_login = ?, login_count = login_count + 1 WHERE email = ?
            ''', (datetime.now().isoformat(), email))
            conn.commit()
            conn.close()
            
            app.logger.info(f"Admin login successful: {email}")
            return True
        else:
            app.logger.warning(f"Failed login attempt: {email}")
            return False
    except Exception as e:
        app.logger.error(f"Error verifying admin: {e}")
        return False

def log_activity(user_id, action, entity_type, entity_id, details=None, ip_address=None, user_agent=None):
    """Log admin activity"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO activity_log (user_id, action, entity_type, entity_id, details, ip_address, user_agent, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            action,
            entity_type,
            entity_id,
            json.dumps(details) if details else None,
            ip_address,
            user_agent,
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    except Exception as e:
        app.logger.error(f"Error logging activity: {e}")

def cleanup_temp_files():
    """Clean up old temporary files"""
    try:
        temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
        if os.path.exists(temp_dir):
            now = time.time()
            for filename in os.listdir(temp_dir):
                filepath = os.path.join(temp_dir, filename)
                if os.path.isfile(filepath):
                    # Remove files older than 1 hour
                    if os.path.getmtime(filepath) < now - 3600:
                        os.remove(filepath)
    except Exception as e:
        app.logger.error(f"Error cleaning temp files: {e}")

# Run cleanup on startup
cleanup_temp_files()

# ==================== API ENDPOINTS ====================

@app.route('/')
@app.route('/index.html')
def serve_frontend():
    """Serve the main HTML file"""
    return send_from_directory('.', 'index.html')

@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    """Serve uploaded files"""
    try:
        # Security check - prevent directory traversal
        if '..' in filename or filename.startswith('/'):
            return jsonify({'error': 'Invalid filename'}), 400
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(file_path):
            app.logger.warning(f"File not found: {filename}")
            return jsonify({'error': 'File not found'}), 404
        
        # Get proper mimetype
        mimetype, _ = mimetypes.guess_type(filename)
        if not mimetype:
            if filename.endswith('.mp4'):
                mimetype = 'video/mp4'
            elif filename.endswith('.pdf'):
                mimetype = 'application/pdf'
            else:
                mimetype = 'application/octet-stream'
        
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename, mimetype=mimetype)
    except Exception as e:
        app.logger.error(f"Error serving file {filename}: {e}")
        return jsonify({'error': 'File not found'}), 404

@app.route('/api/drive-proxy/<file_id>')
def drive_proxy(file_id):
    """Proxy for Google Drive files"""
    return redirect(f'https://drive.google.com/file/d/{file_id}/preview')

# ============ AUTH ENDPOINTS ============
@app.route('/api/auth/login', methods=['POST', 'OPTIONS'])
def login():
    """Admin login endpoint"""
    if request.method == 'OPTIONS':
        return '', 200
        
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
            
        email = data.get('email', '').lower().strip()
        password = data.get('password', '')
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent')
        
        app.logger.info(f"Login attempt: {email}")
        
        if verify_admin(email, password):
            # Get user details
            conn = sqlite3.connect(DATABASE)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT id, name, role, permissions FROM admin_users WHERE email = ?', (email,))
            user = cursor.fetchone()
            conn.close()
            
            # Create session token
            session_token = hashlib.sha256(f"{email}{uuid.uuid4().hex}{time.time()}".encode()).hexdigest()
            
            # Store session
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sessions (id, user_id, token, ip_address, user_agent, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                uuid.uuid4().hex,
                user['id'],
                session_token,
                ip_address,
                user_agent,
                datetime.now().isoformat(),
                (datetime.now().timestamp() + 86400)  # 24 hours
            ))
            conn.commit()
            conn.close()
            
            # Log activity
            log_activity(
                user_id=user['id'],
                action='login',
                entity_type='auth',
                entity_id=email,
                details={'ip': ip_address, 'user_agent': user_agent},
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            return jsonify({
                'success': True,
                'message': 'Login successful',
                'email': email,
                'name': user['name'],
                'role': user['role'],
                'permissions': json.loads(user['permissions']) if user['permissions'] else [],
                'token': session_token
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Invalid email or password'
            }), 401
            
    except Exception as e:
        app.logger.error(f"Login error: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """Admin logout endpoint"""
    try:
        data = request.json
        token = data.get('token')
        
        if token:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM sessions WHERE token = ?', (token,))
            conn.commit()
            conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Logout successful'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/verify', methods=['POST'])
def verify_token():
    """Verify session token"""
    try:
        data = request.json
        token = data.get('token')
        
        if not token:
            return jsonify({'valid': False}), 401
        
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT s.*, u.email, u.name, u.role, u.permissions 
            FROM sessions s
            JOIN admin_users u ON s.user_id = u.id
            WHERE s.token = ? AND s.expires_at > ?
        ''', (token, time.time()))
        
        session = cursor.fetchone()
        conn.close()
        
        if session:
            return jsonify({
                'valid': True,
                'email': session['email'],
                'name': session['name'],
                'role': session['role'],
                'permissions': json.loads(session['permissions']) if session['permissions'] else []
            })
        else:
            return jsonify({'valid': False}), 401
            
    except Exception as e:
        return jsonify({'valid': False, 'error': str(e)}), 500

# ============ CONTENT ENDPOINTS ============
@app.route('/api/content', methods=['GET'])
def get_all_content():
    """Get all content"""
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get filter parameters
        content_type = request.args.get('type')
        category = request.args.get('category')
        featured = request.args.get('featured')
        limit = request.args.get('limit', 100)
        offset = request.args.get('offset', 0)
        
        query = "SELECT * FROM content WHERE status = 'Active'"
        params = []
        
        if content_type and content_type != 'all':
            query += " AND type = ?"
            params.append(content_type)
        
        if category:
            query += " AND category = ?"
            params.append(category)
        
        if featured and featured.lower() == 'true':
            query += " AND featured = 1"
        
        query += " ORDER BY priority DESC, created_date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        
        rows = cursor.fetchall()
        content = []
        
        for row in rows:
            item = dict(row)
            item['displayDate'] = format_date(item['created_date'])
            item['date'] = item['created_date']
            item['displayUpdatedDate'] = format_date(item['updated_date']) if item['updated_date'] else item['displayDate']
            
            # Build media array from image_urls JSON
            media = []
            
            # Handle multiple images
            if item['image_urls']:
                try:
                    image_urls = json.loads(item['image_urls'])
                    for img_url in image_urls:
                        if img_url and isinstance(img_url, dict):
                            media.append({
                                'type': 'image',
                                'url': get_embeddable_url(img_url.get('url', '')),
                                'thumbnail': get_embeddable_url(img_url.get('thumbnail', img_url.get('url', ''))),
                                'size': img_url.get('size', 0),
                                'dimensions': img_url.get('dimensions', None)
                            })
                        elif img_url and isinstance(img_url, str):
                            media.append({
                                'type': 'image',
                                'url': get_embeddable_url(img_url),
                                'thumbnail': get_embeddable_url(img_url)
                            })
                except:
                    # Fallback for single image
                    if item['image_urls']:
                        media.append({
                            'type': 'image',
                            'url': get_embeddable_url(item['image_urls']),
                            'thumbnail': get_embeddable_url(item['image_urls'])
                        })
            
            # Handle video
            if item['video_url']:
                media.append({
                    'type': 'video',
                    'url': get_embeddable_url(item['video_url']),
                    'thumbnail': None
                })
            
            item['media'] = media
            
            # Parse tags
            if item['tags']:
                try:
                    item['tags'] = json.loads(item['tags'])
                except:
                    item['tags'] = item['tags'].split(',') if item['tags'] else []
            else:
                item['tags'] = []
            
            content.append(item)
        
        # Get total count for pagination
        cursor.execute("SELECT COUNT(*) FROM content WHERE status = 'Active'")
        total = cursor.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'content': content,
            'total': total,
            'limit': int(limit),
            'offset': int(offset)
        })
        
    except Exception as e:
        app.logger.error(f"Error getting content: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/content/<content_id>', methods=['GET'])
def get_content(content_id):
    """Get single content item"""
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM content WHERE id = ? AND status = "Active"', (content_id,))
        row = cursor.fetchone()
        
        if not row:
            return jsonify({'error': 'Content not found'}), 404
        
        # Increment view count
        cursor.execute('UPDATE content SET views = views + 1 WHERE id = ?', (content_id,))
        conn.commit()
        
        item = dict(row)
        item['displayDate'] = format_date(item['created_date'])
        item['date'] = item['created_date']
        item['displayUpdatedDate'] = format_date(item['updated_date']) if item['updated_date'] else item['displayDate']
        
        # Build media array
        media = []
        if item['image_urls']:
            try:
                image_urls = json.loads(item['image_urls'])
                for img_url in image_urls:
                    if img_url:
                        media.append({
                            'type': 'image',
                            'url': get_embeddable_url(img_url.get('url', '')),
                            'thumbnail': get_embeddable_url(img_url.get('thumbnail', img_url.get('url', '')))
                        })
            except:
                if item['image_urls']:
                    media.append({
                        'type': 'image',
                        'url': get_embeddable_url(item['image_urls']),
                        'thumbnail': get_embeddable_url(item['image_urls'])
                    })
        
        if item['video_url']:
            media.append({
                'type': 'video',
                'url': get_embeddable_url(item['video_url'])
            })
        
        item['media'] = media
        
        # Parse tags
        if item['tags']:
            try:
                item['tags'] = json.loads(item['tags'])
            except:
                item['tags'] = item['tags'].split(',') if item['tags'] else []
        
        conn.close()
        
        return jsonify(item)
        
    except Exception as e:
        app.logger.error(f"Error getting content {content_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/content', methods=['POST'])
def save_content():
    """Save new content"""
    try:
        data = request.json
        content_data = data.get('data', {})
        files = data.get('files', [])
        
        # Get admin info from token
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'success': False, 'error': 'No token provided'}), 401
            
        admin_info = None
        if token:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM sessions WHERE token = ? AND expires_at > ?', (token, time.time()))
            session = cursor.fetchone()
            if session:
                cursor.execute('SELECT id, email FROM admin_users WHERE id = ?', (session[0],))
                admin_info = cursor.fetchone()
            conn.close()
            
        if not admin_info:
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
        
        content_id = content_data.get('id') or f"content-{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        
        image_urls = []
        video_url = content_data.get('videoUrl', '')
        media_type = ''
        file_count = 0
        
        # Process uploaded files
        for file_data in files:
            filename = file_data.get('name', f"file_{uuid.uuid4().hex}")
            file_type = file_data.get('type', '')
            base64_data = file_data.get('data', '')
            
            saved_file = save_base64_file(base64_data, filename)
            if saved_file:
                file_type_detected = saved_file.get('type', '')
                if file_type_detected == 'image':
                    image_urls.append({
                        'url': saved_file['url'],
                        'thumbnail': saved_file.get('thumbnail', saved_file['url']),
                        'size': saved_file.get('size', 0),
                        'dimensions': saved_file.get('dimensions', None)
                    })
                    media_type = 'image' if not media_type or media_type == 'image' else 'mixed'
                elif file_type_detected == 'video':
                    video_url = saved_file['url']
                    media_type = 'video' if not media_type or media_type == 'video' else 'mixed'
                file_count += 1
        
        # Convert image_urls to JSON
        image_urls_json = json.dumps(image_urls) if image_urls else ''
        
        # Parse tags
        tags = content_data.get('tags', [])
        if isinstance(tags, list):
            tags_json = json.dumps(tags)
        else:
            tags_json = tags
        
        # Save to database
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO content 
            (id, type, title, text, category, image_urls, video_url, created_date, 
             updated_date, status, media_type, file_count, style, priority, tags,
             author, featured, language, seo_title, seo_description, seo_keywords)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            content_id,
            content_data.get('type', 'post'),
            content_data.get('title', ''),
            content_data.get('text', ''),
            content_data.get('category', 'General'),
            image_urls_json,
            video_url,
            now,
            now,
            'Active',
            media_type,
            file_count,
            content_data.get('style', 'default'),
            content_data.get('priority', 0),
            tags_json,
            content_data.get('author', 'KC Jain'),
            content_data.get('featured', 0),
            content_data.get('language', 'en'),
            content_data.get('seo_title', ''),
            content_data.get('seo_description', ''),
            content_data.get('seo_keywords', '')
        ))
        
        conn.commit()
        conn.close()
        
        # Log activity
        if admin_info:
            log_activity(
                user_id=admin_info[0],
                action='create',
                entity_type='content',
                entity_id=content_id,
                details={'type': content_data.get('type'), 'title': content_data.get('title')}
            )
        
        app.logger.info(f"Content saved: {content_id}")
        
        return jsonify({
            'success': True,
            'message': 'Content saved successfully',
            'contentId': content_id,
            'imageUrls': [img['url'] for img in image_urls],
            'thumbnailUrls': [img.get('thumbnail', img['url']) for img in image_urls],
            'videoUrl': get_embeddable_url(video_url),
            'timestamp': now,
            'displayDate': format_date(now)
        })
        
    except Exception as e:
        app.logger.error(f"Error saving content: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/content/<content_id>', methods=['PUT'])
def update_content(content_id):
    """Update existing content"""
    try:
        data = request.json
        content_data = data.get('data', {})
        files = data.get('files', [])
        
        # Get admin info from token
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'success': False, 'error': 'No token provided'}), 401
            
        admin_info = None
        if token:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM sessions WHERE token = ? AND expires_at > ?', (token, time.time()))
            session = cursor.fetchone()
            if session:
                cursor.execute('SELECT id, email FROM admin_users WHERE id = ?', (session[0],))
                admin_info = cursor.fetchone()
            conn.close()
            
        if not admin_info:
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
        
        now = datetime.now().isoformat()
        
        # Get existing content
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM content WHERE id = ?', (content_id,))
        existing = cursor.fetchone()
        
        if not existing:
            return jsonify({'success': False, 'error': 'Content not found'}), 404
        
        # Process new uploaded files
        image_urls = []
        video_url = content_data.get('videoUrl', existing['video_url'] if existing else '')
        media_type = ''
        file_count = 0
        
        for file_data in files:
            filename = file_data.get('name', f"file_{uuid.uuid4().hex}")
            file_type = file_data.get('type', '')
            base64_data = file_data.get('data', '')
            
            saved_file = save_base64_file(base64_data, filename)
            if saved_file:
                file_type_detected = saved_file.get('type', '')
                if file_type_detected == 'image':
                    image_urls.append({
                        'url': saved_file['url'],
                        'thumbnail': saved_file.get('thumbnail', saved_file['url']),
                        'size': saved_file.get('size', 0),
                        'dimensions': saved_file.get('dimensions', None)
                    })
                elif file_type_detected == 'video':
                    video_url = saved_file['url']
                file_count += 1
        
        # If no new images, keep existing ones
        if not image_urls and existing and existing['image_urls']:
            try:
                existing_images = json.loads(existing['image_urls'])
                if isinstance(existing_images, list):
                    image_urls = existing_images
            except:
                pass
        
        # Convert image_urls to JSON
        image_urls_json = json.dumps(image_urls) if image_urls else ''
        
        # Parse tags
        tags = content_data.get('tags', [])
        if isinstance(tags, list):
            tags_json = json.dumps(tags)
        else:
            tags_json = tags if tags else existing['tags']
        
        cursor.execute('''
            UPDATE content SET
                type = ?,
                title = ?,
                text = ?,
                category = ?,
                image_urls = ?,
                video_url = ?,
                updated_date = ?,
                media_type = ?,
                file_count = ?,
                style = ?,
                priority = ?,
                tags = ?,
                author = ?,
                featured = ?,
                language = ?,
                seo_title = ?,
                seo_description = ?,
                seo_keywords = ?
            WHERE id = ?
        ''', (
            content_data.get('type', existing['type']),
            content_data.get('title', existing['title']),
            content_data.get('text', existing['text']),
            content_data.get('category', existing['category']),
            image_urls_json,
            video_url,
            now,
            media_type or existing['media_type'],
            file_count or existing['file_count'],
            content_data.get('style', existing['style']),
            content_data.get('priority', existing['priority']),
            tags_json,
            content_data.get('author', existing['author']),
            content_data.get('featured', existing['featured']),
            content_data.get('language', existing['language']),
            content_data.get('seo_title', existing['seo_title']),
            content_data.get('seo_description', existing['seo_description']),
            content_data.get('seo_keywords', existing['seo_keywords']),
            content_id
        ))
        
        conn.commit()
        conn.close()
        
        # Log activity
        if admin_info:
            log_activity(
                user_id=admin_info[0],
                action='update',
                entity_type='content',
                entity_id=content_id,
                details={'type': content_data.get('type'), 'title': content_data.get('title')}
            )
        
        app.logger.info(f"Content updated: {content_id}")
        
        return jsonify({
            'success': True,
            'message': 'Content updated successfully',
            'contentId': content_id,
            'timestamp': now
        })
        
    except Exception as e:
        app.logger.error(f"Error updating content {content_id}: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/content/<content_id>', methods=['DELETE'])
def delete_content(content_id):
    """Delete content (soft delete)"""
    try:
        # Get admin info from token
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'success': False, 'error': 'No token provided'}), 401
            
        admin_info = None
        if token:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM sessions WHERE token = ? AND expires_at > ?', (token, time.time()))
            session = cursor.fetchone()
            if session:
                cursor.execute('SELECT id, email FROM admin_users WHERE id = ?', (session[0],))
                admin_info = cursor.fetchone()
            conn.close()
            
        if not admin_info:
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('UPDATE content SET status = "Inactive" WHERE id = ?', (content_id,))
        conn.commit()
        conn.close()
        
        # Log activity
        if admin_info:
            log_activity(
                user_id=admin_info[0],
                action='delete',
                entity_type='content',
                entity_id=content_id
            )
        
        app.logger.info(f"Content deleted: {content_id}")
        
        return jsonify({
            'success': True,
            'message': 'Content deleted successfully',
            'contentId': content_id
        })
        
    except Exception as e:
        app.logger.error(f"Error deleting content {content_id}: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ QR CODE ENDPOINTS ============
@app.route('/api/qr', methods=['GET'])
def get_all_qr():
    """Get all QR data"""
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get filter parameters
        health_status = request.args.get('health')
        location = request.args.get('location')
        limit = request.args.get('limit', 100)
        offset = request.args.get('offset', 0)
        
        query = "SELECT * FROM qr_data WHERE status = 'Active'"
        params = []
        
        if health_status:
            query += " AND health_status = ?"
            params.append(health_status)
        
        if location:
            query += " AND location LIKE ?"
            params.append(f'%{location}%')
        
        query += " ORDER BY created_date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        
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
            
            # Parse tree image URLs JSON
            if item['tree_image_urls']:
                try:
                    tree_images = json.loads(item['tree_image_urls'])
                    item['treeImages'] = tree_images
                    
                    # Create media array for frontend
                    media = []
                    for img in tree_images:
                        media.append({
                            'type': 'image',
                            'url': img.get('url', ''),
                            'thumbnail': img.get('thumbnail', img.get('url', ''))
                        })
                    if item['tree_video_url']:
                        media.append({
                            'type': 'video',
                            'url': item['tree_video_url']
                        })
                    item['media'] = media
                except:
                    item['treeImages'] = []
                    item['media'] = []
            else:
                item['treeImages'] = []
                item['media'] = []
            
            qr_list.append(item)
        
        # Get total count
        cursor.execute("SELECT COUNT(*) FROM qr_data WHERE status = 'Active'")
        total = cursor.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'qrData': qr_list,
            'total': total,
            'limit': int(limit),
            'offset': int(offset)
        })
        
    except Exception as e:
        app.logger.error(f"Error getting QR data: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/qr/<qr_id>', methods=['GET'])
def get_qr(qr_id):
    """Get single QR data"""
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM qr_data WHERE id = ? AND status = "Active"', (qr_id,))
        row = cursor.fetchone()
        
        if not row:
            return jsonify({'error': 'QR data not found'}), 404
        
        # Increment scan count
        cursor.execute('UPDATE qr_data SET qr_scan_count = qr_scan_count + 1 WHERE id = ?', (qr_id,))
        conn.commit()
        
        item = dict(row)
        item['displayPlantedDate'] = format_date(item['planted_date'])
        item['displayCreatedDate'] = format_date(item['created_date'])
        item['displayLastMaintenance'] = format_date(item['last_maintenance'])
        item['displayNextMaintenance'] = format_date(item['next_maintenance'])
        
        # Parse tree image URLs JSON
        if item['tree_image_urls']:
            try:
                tree_images = json.loads(item['tree_image_urls'])
                item['treeImages'] = tree_images
                
                # Create media array
                media = []
                for img in tree_images:
                    media.append({
                        'type': 'image',
                        'url': img.get('url', ''),
                        'thumbnail': img.get('thumbnail', img.get('url', ''))
                    })
                if item['tree_video_url']:
                    media.append({
                        'type': 'video',
                        'url': item['tree_video_url']
                    })
                item['media'] = media
            except:
                item['treeImages'] = []
                item['media'] = []
        else:
            item['treeImages'] = []
            item['media'] = []
        
        conn.close()
        
        return jsonify(item)
        
    except Exception as e:
        app.logger.error(f"Error getting QR data {qr_id}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/qr', methods=['POST'])
def generate_qr():
    """Generate QR code for tree"""
    try:
        data = request.json
        qr_data = data.get('data', {})
        files = data.get('files', [])
        
        # Get admin info from token
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'success': False, 'error': 'No token provided'}), 401
            
        admin_info = None
        if token:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM sessions WHERE token = ? AND expires_at > ?', (token, time.time()))
            session = cursor.fetchone()
            if session:
                cursor.execute('SELECT id, email FROM admin_users WHERE id = ?', (session[0],))
                admin_info = cursor.fetchone()
            conn.close()
            
        if not admin_info:
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
        
        qr_id = f"TREE-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now().isoformat()
        
        tree_images = []
        tree_video_url = ''
        
        # Process uploaded files
        for file_data in files:
            filename = file_data.get('name', f"tree_{uuid.uuid4().hex}")
            file_type = file_data.get('type', '')
            base64_data = file_data.get('data', '')
            
            saved_file = save_base64_file(base64_data, filename)
            if saved_file:
                if saved_file.get('type') == 'image':
                    tree_images.append({
                        'url': saved_file['url'],
                        'thumbnail': saved_file.get('thumbnail', saved_file['url']),
                        'size': saved_file.get('size', 0),
                        'dimensions': saved_file.get('dimensions', None)
                    })
                elif saved_file.get('type') == 'video':
                    tree_video_url = saved_file['url']
        
        # Prepare QR data
        qr_text_data = {
            'id': qr_id,
            'treeId': qr_data.get('treeId', ''),
            'treeName': qr_data.get('treeName', ''),
            'scientificName': qr_data.get('scientificName', ''),
            'plantedDate': qr_data.get('plantedDate', now),
            'location': qr_data.get('location', ''),
            'coordinates': qr_data.get('coordinates', ''),
            'plantedBy': qr_data.get('plantedBy', ''),
            'maintenanceBy': qr_data.get('maintenanceBy', ''),
            'treeAge': qr_data.get('treeAge', ''),
            'treeHeight': qr_data.get('treeHeight', ''),
            'description': qr_data.get('description', ''),
            'healthStatus': qr_data.get('healthStatus', 'Good'),
            'lastMaintenance': qr_data.get('lastMaintenance', ''),
            'nextMaintenance': qr_data.get('nextMaintenance', ''),
            'wateringSchedule': qr_data.get('wateringSchedule', ''),
            'generated': format_date(now),
            'imageCount': len(tree_images),
            'hasVideo': bool(tree_video_url),
            'girthSize': qr_data.get('girthSize', ''),
            'canopySize': qr_data.get('canopySize', ''),
            'soilType': qr_data.get('soilType', ''),
            'wateringFrequency': qr_data.get('wateringFrequency', ''),
            'specialNotes': qr_data.get('specialNotes', '')
        }
        
        # Generate QR code image with better error correction
        qr = qrcode.QRCode(
            version=2,
            box_size=10,
            border=4,
            error_correction=qrcode.constants.ERROR_CORRECT_H
        )
        qr.add_data(json.dumps(qr_text_data, indent=2))
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Save QR code with tree name for easy identification
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', qr_data.get('treeName', 'tree'))[:20]
        qr_filename = f"qr_{qr_id}_{clean_name}_{uuid.uuid4().hex[:4]}.png"
        qr_path = os.path.join(app.config['UPLOAD_FOLDER'], 'qrcodes', qr_filename)
        os.makedirs(os.path.dirname(qr_path), exist_ok=True)
        qr_img.save(qr_path, 'PNG', optimize=True)
        
        # Create a styled QR version with tree name
        styled_qr_filename = f"styled_{qr_filename}"
        styled_qr_path = os.path.join(app.config['UPLOAD_FOLDER'], 'qrcodes', styled_qr_filename)
        
        try:
            # Add tree name to QR code
            qr_img_styled = Image.new('RGB', (qr_img.width + 40, qr_img.height + 60), 'white')
            qr_img_styled.paste(qr_img, (20, 20))
            
            draw = ImageDraw.Draw(qr_img_styled)
            try:
                font = ImageFont.truetype("arial.ttf", 20)
            except:
                font = ImageFont.load_default()
            
            tree_name_short = qr_data.get('treeName', 'Tree')[:20]
            draw.text((qr_img_styled.width // 2, qr_img.height + 35), 
                     tree_name_short, fill='black', anchor='mm', font=font)
            
            qr_img_styled.save(styled_qr_path, 'PNG', optimize=True)
            qr_code_url = f'/uploads/qrcodes/{styled_qr_filename}'
        except:
            qr_code_url = f'/uploads/qrcodes/{qr_filename}'
        
        # Convert tree images to JSON
        tree_images_json = json.dumps(tree_images) if tree_images else ''
        
        # Calculate tree age in years/months if planted date provided
        tree_age_years = None
        tree_age_months = None
        if qr_data.get('plantedDate'):
            try:
                planted = datetime.fromisoformat(qr_data['plantedDate'].replace('Z', '+00:00'))
                now_date = datetime.now()
                delta = now_date - planted
                tree_age_years = delta.days // 365
                tree_age_months = (delta.days % 365) // 30
            except:
                pass
        
        # Save to database
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO qr_data 
            (id, tree_id, tree_name, scientific_name, planted_date, location,
             coordinates, planted_by, maintenance_by, tree_age, tree_height,
             description, health_status, last_maintenance, next_maintenance,
             watering_schedule, qr_code_url, tree_image_urls, tree_video_url,
             created_date, updated_date, status, qr_style, tree_age_years,
             tree_age_months, girth_size, canopy_size, soil_type,
             watering_frequency, special_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            str(tree_age_years) if tree_age_years else '',
            qr_data.get('treeHeight', ''),
            qr_data.get('description', ''),
            qr_data.get('healthStatus', 'Good'),
            qr_data.get('lastMaintenance', ''),
            qr_data.get('nextMaintenance', ''),
            qr_data.get('wateringSchedule', ''),
            qr_code_url,
            tree_images_json,
            tree_video_url,
            now,
            now,
            'Active',
            qr_data.get('qrStyle', 'default'),
            tree_age_years,
            tree_age_months,
            qr_data.get('girthSize', ''),
            qr_data.get('canopySize', ''),
            qr_data.get('soilType', ''),
            qr_data.get('wateringFrequency', ''),
            qr_data.get('specialNotes', '')
        ))
        
        conn.commit()
        conn.close()
        
        # Log activity
        if admin_info:
            log_activity(
                user_id=admin_info[0],
                action='create',
                entity_type='qr',
                entity_id=qr_id,
                details={'treeName': qr_data.get('treeName'), 'location': qr_data.get('location')}
            )
        
        app.logger.info(f"QR generated: {qr_id} - {qr_data.get('treeName')}")
        
        return jsonify({
            'success': True,
            'message': 'Tree QR data saved successfully',
            'qrId': qr_id,
            'qrCodeUrl': qr_code_url,
            'qrCodeUrlSimple': f'/uploads/qrcodes/{qr_filename}',
            'treeImages': tree_images,
            'treeVideoUrl': tree_video_url,
            'qrData': qr_text_data,
            'displayPlantedDate': format_date(qr_data.get('plantedDate', now)),
            'displayCreatedDate': format_date(now),
            'timestamp': now
        })
        
    except Exception as e:
        app.logger.error(f"Error generating QR: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/qr/<qr_id>', methods=['PUT'])
def update_qr(qr_id):
    """Update QR data"""
    try:
        data = request.json
        qr_data = data.get('data', {})
        files = data.get('files', [])
        
        # Get admin info from token
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'success': False, 'error': 'No token provided'}), 401
            
        admin_info = None
        if token:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM sessions WHERE token = ? AND expires_at > ?', (token, time.time()))
            session = cursor.fetchone()
            if session:
                cursor.execute('SELECT id, email FROM admin_users WHERE id = ?', (session[0],))
                admin_info = cursor.fetchone()
            conn.close()
            
        if not admin_info:
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
        
        now = datetime.now().isoformat()
        
        # Get existing QR data
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM qr_data WHERE id = ?', (qr_id,))
        existing = cursor.fetchone()
        
        if not existing:
            return jsonify({'success': False, 'error': 'QR data not found'}), 404
        
        tree_images = []
        tree_video_url = existing['tree_video_url'] if existing else ''
        
        # Process new uploaded files
        for file_data in files:
            filename = file_data.get('name', f"tree_{uuid.uuid4().hex}")
            file_type = file_data.get('type', '')
            base64_data = file_data.get('data', '')
            
            saved_file = save_base64_file(base64_data, filename)
            if saved_file:
                if saved_file.get('type') == 'image':
                    tree_images.append({
                        'url': saved_file['url'],
                        'thumbnail': saved_file.get('thumbnail', saved_file['url']),
                        'size': saved_file.get('size', 0)
                    })
                elif saved_file.get('type') == 'video':
                    tree_video_url = saved_file['url']
        
        # If no new images, keep existing ones
        if not tree_images and existing and existing['tree_image_urls']:
            try:
                existing_images = json.loads(existing['tree_image_urls'])
                if isinstance(existing_images, list):
                    tree_images = existing_images
            except:
                pass
        
        # Convert tree images to JSON
        tree_images_json = json.dumps(tree_images) if tree_images else ''
        
        cursor.execute('''
            UPDATE qr_data SET
                tree_name = ?,
                scientific_name = ?,
                planted_date = ?,
                location = ?,
                coordinates = ?,
                planted_by = ?,
                maintenance_by = ?,
                tree_age = ?,
                tree_height = ?,
                description = ?,
                health_status = ?,
                last_maintenance = ?,
                next_maintenance = ?,
                watering_schedule = ?,
                tree_image_urls = ?,
                tree_video_url = ?,
                updated_date = ?,
                qr_style = ?,
                girth_size = ?,
                canopy_size = ?,
                soil_type = ?,
                watering_frequency = ?,
                special_notes = ?
            WHERE id = ?
        ''', (
            qr_data.get('treeName', existing['tree_name']),
            qr_data.get('scientificName', existing['scientific_name']),
            qr_data.get('plantedDate', existing['planted_date']),
            qr_data.get('location', existing['location']),
            qr_data.get('coordinates', existing['coordinates']),
            qr_data.get('plantedBy', existing['planted_by']),
            qr_data.get('maintenanceBy', existing['maintenance_by']),
            qr_data.get('treeAge', existing['tree_age']),
            qr_data.get('treeHeight', existing['tree_height']),
            qr_data.get('description', existing['description']),
            qr_data.get('healthStatus', existing['health_status']),
            qr_data.get('lastMaintenance', existing['last_maintenance']),
            qr_data.get('nextMaintenance', existing['next_maintenance']),
            qr_data.get('wateringSchedule', existing['watering_schedule']),
            tree_images_json,
            tree_video_url,
            now,
            qr_data.get('qrStyle', existing['qr_style']),
            qr_data.get('girthSize', existing['girth_size']),
            qr_data.get('canopySize', existing['canopy_size']),
            qr_data.get('soilType', existing['soil_type']),
            qr_data.get('wateringFrequency', existing['watering_frequency']),
            qr_data.get('specialNotes', existing['special_notes']),
            qr_id
        ))
        
        conn.commit()
        conn.close()
        
        # Log activity
        if admin_info:
            log_activity(
                user_id=admin_info[0],
                action='update',
                entity_type='qr',
                entity_id=qr_id,
                details={'treeName': qr_data.get('treeName')}
            )
        
        app.logger.info(f"QR updated: {qr_id}")
        
        return jsonify({
            'success': True,
            'message': 'QR data updated successfully',
            'qrId': qr_id,
            'timestamp': now
        })
        
    except Exception as e:
        app.logger.error(f"Error updating QR {qr_id}: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/qr/<qr_id>', methods=['DELETE'])
def delete_qr(qr_id):
    """Delete QR data (soft delete)"""
    try:
        # Get admin info from token
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'success': False, 'error': 'No token provided'}), 401
            
        admin_info = None
        if token:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM sessions WHERE token = ? AND expires_at > ?', (token, time.time()))
            session = cursor.fetchone()
            if session:
                cursor.execute('SELECT id, email FROM admin_users WHERE id = ?', (session[0],))
                admin_info = cursor.fetchone()
            conn.close()
            
        if not admin_info:
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('UPDATE qr_data SET status = "Inactive" WHERE id = ?', (qr_id,))
        conn.commit()
        conn.close()
        
        # Log activity
        if admin_info:
            log_activity(
                user_id=admin_info[0],
                action='delete',
                entity_type='qr',
                entity_id=qr_id
            )
        
        app.logger.info(f"QR deleted: {qr_id}")
        
        return jsonify({
            'success': True,
            'message': 'QR data deleted successfully',
            'qrId': qr_id
        })
        
    except Exception as e:
        app.logger.error(f"Error deleting QR {qr_id}: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/qr/scan/<qr_id>', methods=['POST'])
def increment_qr_scan(qr_id):
    """Increment QR scan count"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE qr_data SET qr_scan_count = qr_scan_count + 1 WHERE id = ?
        ''', (qr_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Scan count incremented',
            'qrId': qr_id
        })
        
    except Exception as e:
        app.logger.error(f"Error incrementing scan count for {qr_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/qr/download/<qr_id>', methods=['POST'])
def increment_qr_download(qr_id):
    """Increment QR download count"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE qr_data SET qr_download_count = qr_download_count + 1 WHERE id = ?
        ''', (qr_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Download count incremented'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/qr/print/<qr_id>', methods=['POST'])
def increment_qr_print(qr_id):
    """Increment QR print count"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE qr_data SET qr_print_count = qr_print_count + 1 WHERE id = ?
        ''', (qr_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Print count incremented'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ PROFILE ENDPOINTS ============
@app.route('/api/profile', methods=['GET'])
def get_profile():
    """Get profile configuration"""
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM profile_config WHERE key = "profile-image"')
        row = cursor.fetchone()
        conn.close()
        
        if row:
            # Check if the file still exists
            file_path = row['value'].replace('/uploads/', '')
            full_path = os.path.join(app.config['UPLOAD_FOLDER'], file_path)
            
            if os.path.exists(full_path):
                # Get file info
                file_stat = os.stat(full_path)
                
                return jsonify({
                    'profileImage': row['value'],
                    'thumbnailUrl': row['thumbnail'] or row['value'],
                    'updatedAt': row['updated_at'],
                    'updatedDisplay': format_date(row['updated_at']),
                    'metadata': json.loads(row['metadata']) if row['metadata'] else {},
                    'version': row['version'],
                    'createdAt': row['created_at'],
                    'fileSize': file_stat.st_size,
                    'fileExists': True
                })
            else:
                # File doesn't exist, return default
                return jsonify({
                    'profileImage': '/uploads/profile/default-profile.jpg',
                    'thumbnailUrl': '/uploads/profile/default-profile.jpg',
                    'updatedAt': None,
                    'updatedDisplay': 'Never',
                    'metadata': {'name': 'Default Profile', 'type': 'default'},
                    'fileExists': False
                })
        else:
            return jsonify({
                'profileImage': '/uploads/profile/default-profile.jpg',
                'thumbnailUrl': '/uploads/profile/default-profile.jpg',
                'updatedAt': None,
                'updatedDisplay': 'Never',
                'metadata': {'name': 'Default Profile', 'type': 'default'}
            })
            
    except Exception as e:
        app.logger.error(f"Error getting profile: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/profile', methods=['POST'])
def update_profile():
    """Update profile image"""
    try:
        data = request.json
        image_data = data.get('imageData', '')
        filename = data.get('fileName', 'profile.jpg')
        metadata = data.get('metadata', {})
        
        # Get admin info from token
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'success': False, 'error': 'No token provided'}), 401
            
        admin_info = None
        if token:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM sessions WHERE token = ? AND expires_at > ?', (token, time.time()))
            session = cursor.fetchone()
            if session:
                cursor.execute('SELECT id, email FROM admin_users WHERE id = ?', (session[0],))
                admin_info = cursor.fetchone()
            conn.close()
            
        if not admin_info:
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
        
        # Save file with profile subfolder to keep it separate
        saved_file = save_base64_file(image_data, filename, subfolder='profile')
        
        if saved_file and saved_file.get('url'):
            now = datetime.now().isoformat()
            
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            
            # Delete old profile image file if it exists and is not default
            cursor.execute('SELECT * FROM profile_config WHERE key = "profile-image"')
            old_profile = cursor.fetchone()
            if old_profile:
                old_path = old_profile[1].replace('/uploads/', '')
                if old_path and 'default-profile' not in old_path:
                    full_old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_path)
                    if os.path.exists(full_old_path):
                        try:
                            os.remove(full_old_path)
                            app.logger.info(f"Deleted old profile image: {full_old_path}")
                        except Exception as e:
                            app.logger.error(f"Error deleting old profile: {e}")
            
            # Get current version
            version = 1
            if old_profile and old_profile[4]:  # metadata column
                try:
                    old_metadata = json.loads(old_profile[4])
                    version = old_metadata.get('version', 0) + 1
                except:
                    version = old_profile[5] + 1 if old_profile[5] else 2  # version column
            
            cursor.execute('''
                INSERT OR REPLACE INTO profile_config (key, value, thumbnail, updated_at, metadata, created_at, version)
                VALUES (?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM profile_config WHERE key = "profile-image"), ?), ?)
            ''', (
                'profile-image',
                saved_file['url'],
                saved_file.get('thumbnail', saved_file['url']),
                now,
                json.dumps({**metadata, 'filename': filename, 'version': version}),
                now,
                version
            ))
            
            conn.commit()
            conn.close()
            
            # Log activity
            if admin_info:
                log_activity(
                    user_id=admin_info[0],
                    action='update',
                    entity_type='profile',
                    entity_id='profile-image',
                    details={'version': version}
                )
            
            app.logger.info(f"Profile image updated (v{version})")
            
            return jsonify({
                'success': True,
                'profileImage': saved_file['url'],
                'thumbnailUrl': saved_file.get('thumbnail', saved_file['url']),
                'message': 'Profile image updated successfully',
                'timestamp': now,
                'displayDate': format_date(now),
                'version': version
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to save file'}), 500
            
    except Exception as e:
        app.logger.error(f"Error updating profile: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ STATISTICS ENDPOINT ============
@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get website statistics"""
    try:
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
        
        # Get total views
        cursor.execute("SELECT SUM(views) FROM content WHERE status = 'Active'")
        total_views = cursor.fetchone()[0] or 0
        
        # Get total QR scans
        cursor.execute("SELECT SUM(qr_scan_count) FROM qr_data WHERE status = 'Active'")
        total_qr_scans = cursor.fetchone()[0] or 0
        
        # Get total downloads
        cursor.execute("SELECT SUM(qr_download_count) FROM qr_data WHERE status = 'Active'")
        total_downloads = cursor.fetchone()[0] or 0
        
        # Get total prints
        cursor.execute("SELECT SUM(qr_print_count) FROM qr_data WHERE status = 'Active'")
        total_prints = cursor.fetchone()[0] or 0
        
        # Get content by category
        cursor.execute("SELECT category, COUNT(*) FROM content WHERE status = 'Active' GROUP BY category")
        categories = cursor.fetchall()
        
        # Get QR by health status
        cursor.execute("SELECT health_status, COUNT(*) FROM qr_data WHERE status = 'Active' GROUP BY health_status")
        health_stats = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'cases': cases,
            'posts': posts,
            'blogs': blogs,
            'announcements': announcements,
            'qr': qr_codes,
            'totalContent': cases + posts + blogs + announcements,
            'totalViews': total_views,
            'totalQrScans': total_qr_scans,
            'totalDownloads': total_downloads,
            'totalPrints': total_prints,
            'categories': [{'category': cat[0], 'count': cat[1]} for cat in categories],
            'healthStats': [{'status': stat[0], 'count': stat[1]} for stat in health_stats],
            'updated': datetime.now().isoformat(),
            'displayUpdated': format_date(datetime.now().isoformat())
        })
        
    except Exception as e:
        app.logger.error(f"Error getting stats: {e}")
        return jsonify({'error': str(e)}), 500

# ============ SETTINGS ENDPOINTS ============
@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get website settings"""
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM settings')
        rows = cursor.fetchall()
        
        settings = {}
        for row in rows:
            try:
                value = json.loads(row['value']) if row['value'].startswith('{') or row['value'].startswith('[') else row['value']
            except:
                value = row['value']
            
            settings[row['key']] = {
                'value': value,
                'updated_at': row['updated_at'],
                'display_updated': format_date(row['updated_at']),
                'description': row['description'],
                'type': row['type'],
                'group': row['group_name']
            }
        
        conn.close()
        
        return jsonify(settings)
        
    except Exception as e:
        app.logger.error(f"Error getting settings: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Update website settings"""
    try:
        data = request.json
        key = data.get('key')
        value = data.get('value')
        
        # Get admin info from token
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'success': False, 'error': 'No token provided'}), 401
            
        admin_info = None
        if token:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM sessions WHERE token = ? AND expires_at > ?', (token, time.time()))
            session = cursor.fetchone()
            if session:
                cursor.execute('SELECT id, email FROM admin_users WHERE id = ?', (session[0],))
                admin_info = cursor.fetchone()
            conn.close()
            
        if not admin_info:
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
        
        if not key:
            return jsonify({'success': False, 'error': 'Key is required'}), 400
        
        now = datetime.now().isoformat()
        
        # Convert value to JSON string if it's a dict or list
        if isinstance(value, (dict, list)):
            value_json = json.dumps(value)
        else:
            value_json = str(value)
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Check if key exists
        cursor.execute("SELECT * FROM settings WHERE key = ?", (key,))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute('''
                UPDATE settings SET value = ?, updated_at = ? WHERE key = ?
            ''', (value_json, now, key))
        else:
            cursor.execute('''
                INSERT INTO settings (key, value, updated_at, description, type, group_name)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (key, value_json, now, '', 'string', 'general'))
        
        conn.commit()
        conn.close()
        
        # Log activity
        if admin_info:
            log_activity(
                user_id=admin_info[0],
                action='update',
                entity_type='settings',
                entity_id=key,
                details={'key': key}
            )
        
        app.logger.info(f"Settings updated: {key}")
        
        return jsonify({
            'success': True,
            'message': 'Settings updated successfully',
            'key': key,
            'timestamp': now,
            'displayDate': format_date(now)
        })
        
    except Exception as e:
        app.logger.error(f"Error updating settings: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ ACTIVITY LOG ENDPOINTS ============
@app.route('/api/activity', methods=['GET'])
def get_activity():
    """Get activity log"""
    try:
        # Check admin auth
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Unauthorized'}), 401
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM sessions WHERE token = ? AND expires_at > ?', (token, time.time()))
        session = cursor.fetchone()
        
        if not session:
            return jsonify({'error': 'Invalid token'}), 401
        
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        limit = request.args.get('limit', 50)
        
        cursor.execute('''
            SELECT a.*, u.name, u.email 
            FROM activity_log a
            LEFT JOIN admin_users u ON a.user_id = u.id
            ORDER BY a.created_at DESC
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        activities = []
        
        for row in rows:
            item = dict(row)
            item['displayDate'] = format_date(item['created_at'])
            if item['details']:
                try:
                    item['details'] = json.loads(item['details'])
                except:
                    pass
            activities.append(item)
        
        conn.close()
        
        return jsonify(activities)
        
    except Exception as e:
        app.logger.error(f"Error getting activity: {e}")
        return jsonify({'error': str(e)}), 500

# ============ PING ENDPOINT ============
@app.route('/api/ping', methods=['GET'])
def ping():
    """Health check endpoint"""
    return jsonify({
        'status': 'OK',
        'message': 'KC Jain Advocate Website API',
        'version': '4.4.0-python',
        'timestamp': datetime.now().isoformat(),
        'displayDate': format_date(datetime.now().isoformat()),
        'timezone': 'Asia/Kolkata',
        'database': DATABASE,
        'uploadFolder': UPLOAD_FOLDER,
        'maxFileSize': f"{MAX_CONTENT_LENGTH // (1024*1024)}MB",
        'maxImageSize': f"{MAX_IMAGE_SIZE // (1024*1024)}MB",
        'maxVideoSize': f"{MAX_VIDEO_SIZE // (1024*1024)}MB",
        'features': [
            'File Upload',
            'QR Generation',
            'Statistics',
            'Profile Management',
            'SQLite Database',
            'Multiple Image Support',
            'Admin Authentication',
            'Settings Management',
            'Thumbnail Generation',
            'Scan Tracking',
            'Download Tracking',
            'Print Tracking',
            'Persistent Profile Image',
            'Activity Logging',
            'Session Management',
            'Image Optimization',
            'Styled QR Codes',
            'Category Filtering',
            'Health Status Tracking',
            'Pagination Support'
        ]
    })

    # ============ PROFILE IMAGE ENDPOINTS ============
@app.route('/api/profile/upload', methods=['POST'])
def upload_profile_image():
    """Upload profile image"""
    try:
        # Get admin info from token
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'success': False, 'error': 'No token provided'}), 401
            
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM sessions WHERE token = ? AND CAST(expires_at AS REAL) > ?', 
                      (token, time.time()))
        session = cursor.fetchone()
        
        if not session:
            conn.close()
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
        
        # Get the image data from request
        data = request.json
        image_data = data.get('imageData', '')
        
        if not image_data:
            return jsonify({'success': False, 'error': 'No image data provided'}), 400
        
        # Process the image
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        
        # Decode image
        image_bytes = base64.b64decode(image_data)
        
        # Generate unique filename
        filename = f"profile_{uuid.uuid4().hex}.jpg"
        file_path = os.path.join(UPLOAD_FOLDER, 'profile', filename)
        
        # Save image
        with open(file_path, 'wb') as f:
            f.write(image_bytes)
        
        # Optimize image
        try:
            img = Image.open(file_path)
            # Resize if too large
            if max(img.size) > 800:
                img.thumbnail((800, 800), Image.Resampling.LANCZOS)
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'LA', 'P'):
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = rgb_img
            img.save(file_path, optimize=True, quality=85)
        except Exception as e:
            app.logger.error(f"Error optimizing image: {e}")
        
        # Create thumbnail
        thumbnail_filename = f"thumb_{filename}"
        thumbnail_path = os.path.join(UPLOAD_FOLDER, 'profile', thumbnail_filename)
        try:
            img = Image.open(file_path)
            img.thumbnail((300, 300), Image.Resampling.LANCZOS)
            img.save(thumbnail_path, optimize=True, quality=85)
        except Exception as e:
            app.logger.error(f"Error creating thumbnail: {e}")
            thumbnail_path = file_path
            thumbnail_filename = filename
        
        # Update database
        profile_url = f'/uploads/profile/{filename}'
        thumbnail_url = f'/uploads/profile/{thumbnail_filename}'
        
        # Check if profile config exists
        cursor.execute("SELECT * FROM profile_config WHERE key = 'profile-image'")
        existing = cursor.fetchone()
        
        if existing:
            # Delete old image files if they exist
            try:
                old_value = existing[1]  # value column
                if old_value and '/uploads/profile/' in old_value:
                    old_filename = old_value.replace('/uploads/profile/', '')
                    old_path = os.path.join(UPLOAD_FOLDER, 'profile', old_filename)
                    if os.path.exists(old_path) and 'default-profile' not in old_path:
                        os.remove(old_path)
                    
                    # Also delete old thumbnail
                    old_thumb = existing[2]  # thumbnail column
                    if old_thumb and '/uploads/profile/' in old_thumb:
                        old_thumb_filename = old_thumb.replace('/uploads/profile/', '')
                        old_thumb_path = os.path.join(UPLOAD_FOLDER, 'profile', old_thumb_filename)
                        if os.path.exists(old_thumb_path) and 'default-profile' not in old_thumb_path:
                            os.remove(old_thumb_path)
            except Exception as e:
                app.logger.error(f"Error deleting old profile: {e}")
            
            # Update existing record
            cursor.execute('''
                UPDATE profile_config 
                SET value = ?, thumbnail = ?, updated_at = ?
                WHERE key = 'profile-image'
            ''', (profile_url, thumbnail_url, datetime.now().isoformat()))
        else:
            # Insert new record
            cursor.execute('''
                INSERT INTO profile_config (key, value, thumbnail, updated_at)
                VALUES (?, ?, ?, ?)
            ''', ('profile-image', profile_url, thumbnail_url, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Profile image uploaded successfully',
            'profileImage': profile_url,
            'thumbnailUrl': thumbnail_url
        })
        
    except Exception as e:
        app.logger.error(f"Error uploading profile image: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/profile', methods=['GET'])
def get_profile():
    """Get profile image"""
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM profile_config WHERE key = 'profile-image'")
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return jsonify({
                'profileImage': row['value'],
                'thumbnailUrl': row['thumbnail'] or row['value']
            })
        else:
            # Return default profile
            return jsonify({
                'profileImage': '/uploads/profile/default-profile.jpg',
                'thumbnailUrl': '/uploads/profile/default-profile.jpg'
            })
            
    except Exception as e:
        app.logger.error(f"Error getting profile: {e}")
        return jsonify({'error': str(e)}), 500

# ============ ERROR HANDLERS ============
@app.errorhandler(404)
def not_found_error(error):
    app.logger.warning(f"404 error: {request.path}")
    return jsonify({'error': 'Not found', 'status': 404, 'path': request.path}), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"500 error: {error}")
    return jsonify({'error': 'Internal server error', 'status': 500}), 500

@app.errorhandler(413)
def too_large_error(error):
    app.logger.warning(f"413 error: File too large")
    return jsonify({'error': 'File too large', 'status': 413}), 413

# ============ MAIN ============
if __name__ == '__main__':
    print("=" * 70)
    print(" KC Jain Advocate Website - Python Backend v4.4")
    print("=" * 70)
    print(f" Database: {DATABASE}")
    print(f" Upload folder: {UPLOAD_FOLDER}")
    print(f" Max file size: {MAX_CONTENT_LENGTH // (1024*1024)}MB")
    print(f" Max image size: {MAX_IMAGE_SIZE // (1024*1024)}MB")
    print(f" Max video size: {MAX_VIDEO_SIZE // (1024*1024)}MB")
    print("=" * 70)
    print(" Features:")
    print("  ✓ Content Management (Cases, Posts, Blogs, Announcements)")
    print("  ✓ QR Code Generation for Trees")
    print("  ✓ Profile Image Management")
    print("  ✓ Admin Authentication")
    print("  ✓ File Upload (Images, Videos, Documents)")
    print("  ✓ Statistics Tracking")
    print("  ✓ Activity Logging")
    print("  ✓ Settings Management")
    print("=" * 70)
    print(" Starting server at http://localhost:5000")
    print(" Press Ctrl+C to stop")
    print("=" * 70)
    
    # Run the app
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        threaded=True
    )
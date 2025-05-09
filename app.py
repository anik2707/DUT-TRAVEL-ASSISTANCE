from flask import Flask, render_template, redirect, url_for, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from math import radians, sin, cos, sqrt, atan2
from flask_socketio import SocketIO, emit, join_room, leave_room

# Initialize the Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a strong secret key in production

# Database configuration (SQLite)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db = SQLAlchemy(app)

# Setup Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Setup Flask-SocketIO
socketio = SocketIO(app)

# Define the User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    address = db.Column(db.String(200))
    adhar = db.Column(db.String(20))
    phone = db.Column(db.String(15))
    vehicle = db.Column(db.String(20))
    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    is_available = db.Column(db.Boolean, default=False)

from flask_migrate import Migrate
migrate = Migrate(app, db)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            login_user(user)
            return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        address = request.form['address']
        adhar = request.form['adhar']
        phone = request.form['phone']
        vehicle = request.form['vehicle']
        username = request.form['username']
        password = request.form['password']

        new_user = User(name=name, address=address, adhar=adhar, phone=phone, vehicle=vehicle, username=username, password=password)
        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for('login'))

    return render_template('signup.html', registered=False)

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

# @app.route('/notifications')
# def notifications():
#     return render_template('notification_accept.html')  # Notifications page for accepting SOS requests

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))




def calculate_distance(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    R = 6371
    return R * c

@app.route('/update_location', methods=['POST'])
@login_required
def update_location():
    data = request.get_json()
    current_user.latitude = data['lat']
    current_user.longitude = data['lng']
    db.session.commit()
    socketio.emit('location_update', {
        'user_id': current_user.id,
        'lat': current_user.latitude,
        'lng': current_user.longitude
    }, room=f'user_{current_user.id}')
    return {'status': 'success'}

# @app.route('/send_sos', methods=['POST'])
# @login_required
# def send_sos():
#     user_lat = current_user.latitude
#     user_lng = current_user.longitude
#     nearby_users = User.query.filter_by(is_available=True).all()
#     helpers = []

#     for user in nearby_users:
#         if user.latitude and user.longitude:
#             distance = calculate_distance(user.latitude, user.longitude, user_lat, user_lng)
#             if distance <= 3:
#                 helpers.append(user)

#     for helper in helpers:
#         socketio.emit('new_sos', {
#             'sos_user_id': current_user.id,
#             'name': current_user.name,
#             'lat': current_user.latitude,
#             'lng': current_user.longitude
#         }, room=f'user_{helper.id}')

#     return {'helpers': [user.id for user in helpers]}


from datetime import datetime

class HelpRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sos_user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    helper_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    status = db.Column(db.String(50), default='accepted')



@app.route('/send_sos', methods=['POST'])
@login_required
def send_sos():
    user_lat = current_user.latitude
    user_lng = current_user.longitude
    nearby_users = User.query.filter_by(is_available=True).all()
    helpers = []

    for user in nearby_users:
        if user.latitude and user.longitude:
            distance = calculate_distance(user.latitude, user.longitude, user_lat, user_lng)
            if distance <= 3:
                helpers.append(user)

    for helper in helpers:
        socketio.emit('new_sos', {
            'sos_user_id': current_user.id,
            'name': current_user.name,
            'lat': current_user.latitude,
            'lng': current_user.longitude,
            'phone_number': current_user.phone  # Added phone number here
        }, room=f'user_{helper.id}')

    return {'helpers': [user.id for user in helpers]}


# @app.route('/accept_sos', methods=['POST'])
# @login_required
# def accept_sos():
#     data = request.get_json()
#     sos_user_id = data['sos_user_id']
#     socketio.emit('sos_accepted', {
#         'helper_id': current_user.id,
#         'helper_name': current_user.name,
#         'lat': current_user.latitude,
#         'lng': current_user.longitude
#     }, room=f'user_{sos_user_id}')
#     return {'status': 'accepted'}

@app.route('/accept_sos', methods=['POST'])
@login_required
def accept_sos():
    data = request.get_json()
    sos_user_id = data['sos_user_id']
    lat = data.get('lat', current_user.latitude)
    lng = data.get('lng', current_user.longitude)

    # Save the accepted help to DB
    new_help = HelpRequest(
        sos_user_id=sos_user_id,
        helper_id=current_user.id,
        lat=lat,
        lng=lng,
        status='accepted'
    )
    db.session.add(new_help)
    db.session.commit()

    # Notify the original SOS sender
    socketio.emit('sos_accepted', {
        'helper_id': current_user.id,
        'helper_name': current_user.name,
        'lat': current_user.latitude,
        'lng': current_user.longitude,
        'phone_number': current_user.phone
    }, room=f'user_{sos_user_id}')

    return {'status': 'accepted'}


@socketio.on('join')
def on_join(data):
    user_id = data['user_id']
    join_room(f'user_{user_id}')

@socketio.on('leave')
def on_leave(data):
    user_id = data['user_id']
    leave_room(f'user_{user_id}')

@socketio.on('sos_request')
def handle_sos_request(data):
    emit('new_sos', data, broadcast=True)

@socketio.on('accept_sos')
def handle_accept(data):
    emit('accept_sos_response', {'message': 'SOS accepted', 'user_id': data['user_id']}, broadcast=True)

@app.route('/notifications')
@login_required
def notifications():
    return render_template('notification_accept.html')





if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True)
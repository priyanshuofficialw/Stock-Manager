# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import os

app = Flask(__name__)
app.secret_key = 'secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.permanent_session_lifetime = timedelta(days=30)
db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    role = db.Column(db.String(10))

class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(100))
    quantity = db.Column(db.Integer)
    unit_price = db.Column(db.Float)
    low_stock_threshold = db.Column(db.Integer, default=5)

class StockUsage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    item_id = db.Column(db.Integer, db.ForeignKey('stock.id'))
    used_quantity = db.Column(db.Integer)
    date = db.Column(db.DateTime, default=datetime.utcnow)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Float)
    method = db.Column(db.String(50))
    date = db.Column(db.DateTime, default=datetime.utcnow)

class UsageLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    mobile = db.Column(db.String(15))
    item = db.Column(db.String(100))
    quantity = db.Column(db.Integer)
    payment = db.Column(db.Float)
    note = db.Column(db.String(200))
    date = db.Column(db.DateTime, default=datetime.utcnow)

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email, password=password).first()
        if user:
            session.permanent = 'remember' in request.form  # Remember Me checkbox
            session['user_id'] = user.id
            session['role'] = user.role
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user = User.query.get(session['user_id'])
    stock = Stock.query.all()
    logs = UsageLog.query.order_by(UsageLog.date.desc()).all()

    if user.role == 'owner':
        usage = db.session.query(StockUsage, User.name, Stock.item_name)\
            .join(User, StockUsage.staff_id == User.id)\
            .join(Stock, StockUsage.item_id == Stock.id)\
            .order_by(StockUsage.date.desc()).all()
        low_stock_items = [item for item in stock if item.quantity < item.low_stock_threshold]
        return render_template('owner_dashboard.html', stock=stock, usage=usage, logs=logs, low_stock_items=low_stock_items, str=str)
    else:
        return render_template('staff_dashboard.html', stock=stock, logs=logs, str=str)

@app.route('/add_stock', methods=['POST'])
def add_stock():
    item_name = request.form['item_name'].strip().lower()
    quantity = int(request.form['quantity'])
    unit_price = float(request.form['unit_price'])
    threshold = int(request.form['low_stock_threshold'])
    existing_item = Stock.query.filter(db.func.lower(Stock.item_name) == item_name).first()
    if existing_item:
        existing_item.quantity += quantity
        existing_item.unit_price = unit_price
        existing_item.low_stock_threshold = threshold
    else:
        stock = Stock(item_name=item_name, quantity=quantity, unit_price=unit_price, low_stock_threshold=threshold)
        db.session.add(stock)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/edit_stock/<int:id>', methods=['GET', 'POST'])
def edit_stock(id):
    item = Stock.query.get(id)
    if request.method == 'POST':
        item.item_name = request.form['item_name']
        item.quantity = int(request.form['quantity'])
        item.unit_price = float(request.form['unit_price'])
        item.low_stock_threshold = int(request.form['low_stock_threshold'])
        db.session.commit()
        return redirect(url_for('dashboard'))
    return f"<form method='POST'><input name='item_name' value='{item.item_name}'><input name='quantity' value='{item.quantity}'><input name='unit_price' value='{item.unit_price}'><input name='low_stock_threshold' value='{item.low_stock_threshold}'><button>Save</button></form>"

@app.route('/delete_stock/<int:id>')
def delete_stock(id):
    item = Stock.query.get(id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/use_stock', methods=['POST'])
def use_stock():
    item_id = int(request.form['item_id'])
    qty = int(request.form['used_quantity'])
    stock = Stock.query.get(item_id)
    if stock.quantity < qty:
        return "Not enough stock"
    stock.quantity -= qty
    usage = StockUsage(staff_id=session['user_id'], item_id=item_id, used_quantity=qty)
    db.session.add(usage)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/log_usage', methods=['POST'])
def log_usage():
    name = request.form.get('name')
    mobile = request.form.get('mobile')
    item = request.form.get('item')
    quantity = int(request.form.get('quantity'))
    payment = float(request.form.get('payment') or 0)
    note = request.form.get('note')

    usage = UsageLog(name=name, mobile=mobile, item=item, quantity=quantity, payment=payment, note=note, date=datetime.now())
    db.session.add(usage)
    db.session.commit()

    os.makedirs('static/bills', exist_ok=True)
    bill_path = f'static/bills/bill_{usage.id}.png'

    img = Image.new('RGB', (400, 400), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    lines = [
        f"Goldsure Inventory Bill", f"Bill No: {usage.id}", f"Name: {name}", f"Mobile: {mobile}",
        f"Item: {item}", f"Quantity: {quantity}", f"Payment: Rs. {payment}",
        f"Note: {note}", f"Date: {usage.date.strftime('%Y-%m-%d %H:%M:%S')}"
    ]
    y = 20
    for line in lines:
        draw.text((10, y), line, font=font, fill=(0, 0, 0))
        y += 25
    img.save(bill_path)

    return redirect(url_for('dashboard'))

@app.route('/bills')
def bills():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    logs = UsageLog.query.order_by(UsageLog.date.desc()).all()
    return render_template('bills.html', logs=logs, str=str)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(email='admin@goldsure.com').first():
            db.session.add(User(name='Goldsure Admin', email='admin@goldsure.com', password='agarwal8623', role='owner'))
        if not User.query.filter_by(email='staff@goldsure.com').first():
            db.session.add(User(name='Goldsure Staff', email='staff@goldsure.com', password='staff2639', role='staff'))
        db.session.commit()
    app.run(debug=True)

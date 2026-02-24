import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла (только для локальной разработки)
load_dotenv()

# Создаём экземпляр приложения
app = Flask(__name__)

# Конфигурация
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///blog.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация базы данных
db = SQLAlchemy(app)

# Модель Post
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Post {self.title}>'

# Маршруты
@app.route('/')
def index():
    posts = Post.query.order_by(Post.date_posted.desc()).all()
    return render_template('index.html', posts=posts)

@app.route('/post/<int:post_id>')
def post(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('post.html', post=post)

@app.route('/create', methods=['GET', 'POST'])
def create():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        new_post = Post(title=title, content=content)
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('create.html')

@app.route('/about')
def about():
    return render_template('about.html')

# Обработка ошибки 404
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# Создание таблиц базы данных (если не существуют)
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import InputRequired, Length, Email, EqualTo
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
from dotenv import load_dotenv

# Загружаем переменные окружения из .env (для локальной разработки)
load_dotenv()

app = Flask(__name__)

# Конфигурация
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///blog.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Инициализация Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите, чтобы увидеть эту страницу.'

# Инициализация Flask-Migrate
migrate = Migrate(app, db)

# ----------------------------------------------------------------------
# МОДЕЛИ БАЗЫ ДАННЫХ
# ----------------------------------------------------------------------

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    posts = db.relationship('Post', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    def __repr__(self):
        return f'<Post {self.title}>'


class UserLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.Text, nullable=True)
    user = db.relationship('User', backref='logs')

    def __repr__(self):
        return f'<UserLog {self.action} at {self.timestamp}>'


# ----------------------------------------------------------------------
# ЗАГРУЗЧИК ПОЛЬЗОВАТЕЛЯ
# ----------------------------------------------------------------------
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ----------------------------------------------------------------------
# ФОРМЫ
# ----------------------------------------------------------------------
class RegistrationForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[InputRequired(), Length(min=4, max=80)])
    email = StringField('Email', validators=[InputRequired(), Email()])
    password = PasswordField('Пароль', validators=[InputRequired(), Length(min=6)])
    confirm = PasswordField('Повторите пароль', validators=[InputRequired(), EqualTo('password')])
    submit = SubmitField('Зарегистрироваться')


class LoginForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[InputRequired()])
    password = PasswordField('Пароль', validators=[InputRequired()])
    submit = SubmitField('Войти')


# ----------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ЛОГИРОВАНИЯ
# ----------------------------------------------------------------------
def log_user_action(user, action, details=None):
    log = UserLog(user_id=user.id if user else None, action=action, details=details)
    db.session.add(log)
    db.session.commit()


# ----------------------------------------------------------------------
# МАРШРУТЫ
# ----------------------------------------------------------------------

@app.route('/')
def index():
    """Главная страница с полноэкранным изображением"""
    return render_template('only_image.html')


@app.route('/price')
def price():
    """Страница с ценами"""
    return render_template('price.html')


@app.route('/examples')
def examples():
    """Страница с примерами работ"""
    return render_template('examples.html')


@app.route('/support', methods=['GET', 'POST'])
def support():
    """Страница поддержки"""
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        message = request.form['message']
        # Здесь можно добавить отправку email или сохранение в БД
        flash('Спасибо за обращение! Мы ответим вам в ближайшее время.', 'success')
        return redirect(url_for('support'))
    return render_template('support.html')


@app.route('/personal_account')
@login_required
def personal_account():
    """Личный кабинет пользователя"""
    return render_template('personal_account.html')


@app.route('/design')
def design_gallery():
    """Галерея дизайна и цен"""
    return render_template('design_gallery.html')


@app.route('/post/<int:post_id>')
def post(post_id):
    """Страница отдельного поста"""
    post = Post.query.get_or_404(post_id)
    return render_template('post.html', post=post)


@app.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Создание нового поста (только для авторизованных)"""
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        new_post = Post(title=title, content=content, user_id=current_user.id)
        db.session.add(new_post)
        db.session.commit()
        log_user_action(current_user, 'create_post', f'Post id: {new_post.id}')
        flash('Пост успешно создан!', 'success')
        return redirect(url_for('index'))
    return render_template('create.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Регистрация нового пользователя"""
    if current_user.is_authenticated:
        return redirect(url_for('personal_account'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash('Имя пользователя уже занято.', 'danger')
            return render_template('register.html', form=form)
        if User.query.filter_by(email=form.email.data).first():
            flash('Email уже зарегистрирован.', 'danger')
            return render_template('register.html', form=form)
        
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        log_user_action(user, 'register')
        
        flash('Регистрация прошла успешно! Теперь вы можете войти.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Вход пользователя"""
    if current_user.is_authenticated:
        return redirect(url_for('personal_account'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            log_user_action(user, 'login')
            flash('Вы успешно вошли в систему.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('personal_account'))
        else:
            flash('Неверное имя пользователя или пароль.', 'danger')
    
    return render_template('login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    """Выход пользователя"""
    log_user_action(current_user, 'logout')
    logout_user()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('index'))


# ----------------------------------------------------------------------
# ОБРАБОТКА ОШИБОК
# ----------------------------------------------------------------------
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


# ----------------------------------------------------------------------
# СОЗДАНИЕ ТАБЛИЦ ПРИ ЗАПУСКЕ
# ----------------------------------------------------------------------
with app.app_context():
    db.create_all()


# ----------------------------------------------------------------------
# ЗАПУСК (ТОЛЬКО ДЛЯ ЛОКАЛЬНОЙ РАЗРАБОТКИ)
# ----------------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True)
import os
import secrets
import threading
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth
from flask_mail import Mail, Message

# Загружаем переменные окружения из .env
load_dotenv()

app = Flask(__name__)

# Конфигурация
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///blog.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_NAME'] = 'myblog_session'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# ==================== НАСТРОЙКИ ПОЧТЫ (MAIL.RU) ====================
# Прописываем напрямую для надёжности
app.config['MAIL_SERVER'] = 'smtp.mail.ru'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'pshenichka.oleg@mail.ru'
app.config['MAIL_PASSWORD'] = '7QtaWPZC4Q1JOBHceaTG'  # ВСТАВЬТЕ СЮДА ПАРОЛЬ!
app.config['MAIL_DEFAULT_SENDER'] = 'pshenichka.oleg@mail.ru'

print("=== НАСТРОЙКИ ПОЧТЫ ===")
print(f"MAIL_SERVER: {app.config['MAIL_SERVER']}")
print(f"MAIL_USERNAME: {app.config['MAIL_USERNAME']}")
print(f"MAIL_DEFAULT_SENDER: {app.config['MAIL_DEFAULT_SENDER']}")
print(f"MAIL_PASSWORD загружен: {'Да' if app.config['MAIL_PASSWORD'] else 'Нет'}")
print("=======================")

# Инициализация Mail
mail = Mail(app)

db = SQLAlchemy(app)

# Инициализация Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'email_login'
login_manager.login_message = 'Пожалуйста, войдите, чтобы увидеть эту страницу.'

# Инициализация Flask-Migrate
migrate = Migrate(app, db)

# Инициализация OAuth
oauth = OAuth(app)

# Регистрация Google OAuth
google = oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile',
        'prompt': 'select_account'
    }
)

# Регистрация GitHub OAuth
github = oauth.register(
    name='github',
    client_id=os.getenv('GITHUB_CLIENT_ID'),
    client_secret=os.getenv('GITHUB_CLIENT_SECRET'),
    access_token_url='https://github.com/login/oauth/access_token',
    authorize_url='https://github.com/login/oauth/authorize',
    api_base_url='https://api.github.com/',
    client_kwargs={'scope': 'user:email'},
)


# ----------------------------------------------------------------------
# МОДЕЛИ БАЗЫ ДАННЫХ
# ----------------------------------------------------------------------

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=True)
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    github_id = db.Column(db.String(100), unique=True, nullable=True)
    avatar = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    posts = db.relationship('Post', backref='author', lazy=True)

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
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ЛОГИРОВАНИЯ
# ----------------------------------------------------------------------
def log_user_action(user, action, details=None):
    log = UserLog(user_id=user.id if user else None, action=action, details=details)
    db.session.add(log)
    db.session.commit()


# ==================== ФУНКЦИИ ДЛЯ ОТПРАВКИ ПОЧТЫ ====================

def send_async_email(app, msg):
    """Отправка email в фоновом потоке"""
    with app.app_context():
        try:
            print(f"📨 Отправка письма на {msg.recipients}...")
            mail.send(msg)
            print(f"✅ Письмо успешно отправлено!")
        except Exception as e:
            print(f"❌ Ошибка отправки: {str(e)}")


def send_support_email(name, email, message):
    """Отправка письма из формы поддержки"""
    try:
        # Явно указываем отправителя
        msg = Message(
            subject=f'📬 Новое сообщение в поддержку от {name}',
            sender='pshenichka.oleg@mail.ru',
            recipients=['pshenichka.oleg@mail.ru'],
            reply_to=email
        )
        
        msg.body = f"""
Новое сообщение от пользователя:

👤 Имя: {name}
📧 Email: {email}
💬 Сообщение:
{message}

---
Это письмо отправлено автоматически с вашего сайта.
        """
        
        # Отправляем в фоновом потоке
        thread = threading.Thread(target=send_async_email, args=(app, msg))
        thread.daemon = True
        thread.start()
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при подготовке письма: {str(e)}")
        return False


# ----------------------------------------------------------------------
# МАРШРУТЫ
# ----------------------------------------------------------------------

@app.route('/')
def index():
    """Главная страница"""
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
        
        if send_support_email(name, email, message):
            flash('✅ Спасибо за обращение! Мы получили ваше сообщение и ответим в ближайшее время.', 'success')
        else:
            flash('❌ Произошла ошибка при отправке. Пожалуйста, попробуйте позже.', 'danger')
        
        return redirect(url_for('support'))
    
    return render_template('support.html')


@app.route('/personal_account')
@login_required
def personal_account():
    """Личный кабинет пользователя"""
    return render_template('personal_account.html')


@app.route('/post/<int:post_id>')
def post(post_id):
    """Страница отдельного поста"""
    post = Post.query.get_or_404(post_id)
    return render_template('post.html', post=post)


@app.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Создание нового поста"""
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


@app.route('/logout')
@login_required
def logout():
    """Выход пользователя"""
    log_user_action(current_user, 'logout')
    logout_user()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('index'))


# ==================== OAuth МАРШРУТЫ ====================

@app.route('/login/email', methods=['GET', 'POST'])
def email_login():
    """Вход через email"""
    if request.method == 'POST':
        email = request.form.get('email')
        
        if not email:
            flash('Введите email', 'danger')
            return redirect(url_for('email_login'))
        
        user = User.query.filter_by(email=email).first()
        
        if not user:
            base_username = email.split('@')[0]
            username = base_username
            counter = 1
            while User.query.filter_by(username=username).first():
                username = f"{base_username}_{counter}"
                counter += 1
            
            user = User(
                username=username,
                email=email
            )
            db.session.add(user)
            db.session.commit()
            log_user_action(user, 'register_email')
            flash('Аккаунт создан! Вы автоматически вошли.', 'success')
        else:
            flash('Добро пожаловать!', 'success')
        
        login_user(user)
        log_user_action(user, 'login_email')
        
        return redirect(url_for('personal_account'))
    
    return render_template('email_login.html')


@app.route('/login/google')
def google_login():
    """Вход через Google"""
    if current_user.is_authenticated:
        return redirect(url_for('personal_account'))
    
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route('/auth/google/callback')
def google_callback():
    """Обработка callback от Google"""
    try:
        token = google.authorize_access_token()
        user_info = google.parse_id_token(token)
        
        google_id = user_info.get('sub')
        email = user_info.get('email')
        name = user_info.get('name', email.split('@')[0])
        picture = user_info.get('picture')
        
        user = User.query.filter_by(google_id=google_id).first()
        
        if not user:
            user = User.query.filter_by(email=email).first()
            
            if user:
                user.google_id = google_id
                user.avatar = picture
                flash('Ваш аккаунт теперь привязан к Google!', 'success')
            else:
                base_username = name.replace(' ', '_').lower()
                username = base_username
                counter = 1
                while User.query.filter_by(username=username).first():
                    username = f"{base_username}_{counter}"
                    counter += 1
                
                user = User(
                    username=username,
                    email=email,
                    google_id=google_id,
                    avatar=picture
                )
                db.session.add(user)
                flash('Регистрация через Google прошла успешно!', 'success')
            
            db.session.commit()
            log_user_action(user, 'register_google')
        
        login_user(user)
        log_user_action(user, 'login_google')
        
        return redirect(url_for('personal_account'))
        
    except Exception as e:
        flash(f'Ошибка при входе через Google: {str(e)}', 'danger')
        return redirect(url_for('email_login'))


@app.route('/login/github')
def github_login():
    """Вход через GitHub"""
    if current_user.is_authenticated:
        return redirect(url_for('personal_account'))
    
    redirect_uri = url_for('github_callback', _external=True)
    return github.authorize_redirect(redirect_uri)


@app.route('/auth/github/callback')
def github_callback():
    """Обработка callback от GitHub"""
    try:
        token = github.authorize_access_token()
        
        resp = github.get('user', token=token)
        user_info = resp.json()
        
        github_id = str(user_info.get('id'))
        email = user_info.get('email')
        name = user_info.get('name') or user_info.get('login')
        avatar = user_info.get('avatar_url')
        
        if not email:
            emails_resp = github.get('user/emails', token=token)
            emails = emails_resp.json()
            for email_data in emails:
                if email_data.get('primary') and email_data.get('verified'):
                    email = email_data.get('email')
                    break
            if not email and emails:
                email = emails[0].get('email')
        
        if not email:
            flash('Не удалось получить email от GitHub', 'danger')
            return redirect(url_for('email_login'))
        
        user = User.query.filter_by(github_id=github_id).first()
        
        if not user:
            user = User.query.filter_by(email=email).first()
            
            if user:
                user.github_id = github_id
                user.avatar = avatar
                flash('Ваш аккаунт теперь привязан к GitHub!', 'success')
            else:
                base_username = name.replace(' ', '_').lower()
                username = base_username
                counter = 1
                while User.query.filter_by(username=username).first():
                    username = f"{base_username}_{counter}"
                    counter += 1
                
                user = User(
                    username=username,
                    email=email,
                    github_id=github_id,
                    avatar=avatar
                )
                db.session.add(user)
                flash('Регистрация через GitHub прошла успешно!', 'success')
            
            db.session.commit()
            log_user_action(user, 'register_github')
        
        login_user(user)
        log_user_action(user, 'login_github')
        
        return redirect(url_for('personal_account'))
        
    except Exception as e:
        flash(f'Ошибка при входе через GitHub: {str(e)}', 'danger')
        return redirect(url_for('email_login'))


# ==================== МАРШРУТЫ ДЛЯ ТАРИФОВ ====================

@app.route('/tarif/start')
def tarif_start():
    return render_template('tarif_start.html')

@app.route('/tarif/business')
def tarif_business():
    return render_template('tarif_business.html')

@app.route('/tarif/corporate')
def tarif_corporate():
    return render_template('tarif_corporate.html')


# ==================== ТЕСТОВЫЕ МАРШРУТЫ ====================

@app.route('/test-mailru')
def test_mailru():
    """Тест Mail.ru почты"""
    try:
        msg = Message(
            subject='✅ Тест Mail.ru',
            sender='pshenichka.oleg@mail.ru',
            recipients=['pshenichka.oleg@mail.ru']
        )
        msg.body = 'Если вы это читаете — Mail.ru работает!'
        mail.send(msg)
        return '✅ Письмо через Mail.ru отправлено! Проверьте почту.'
    except Exception as e:
        return f'❌ Ошибка: {str(e)}'

@app.route('/routes')
def list_routes():
    """Показать все доступные маршруты"""
    import urllib
    output = []
    for rule in app.url_map.iter_rules():
        methods = ','.join(rule.methods)
        line = urllib.parse.unquote(f"{rule.endpoint}: {rule.rule} [{methods}]")
        output.append(line)
    return '<br>'.join(output)


# ==================== ОБРАБОТЧИКИ ОШИБОК ====================

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


# ----------------------------------------------------------------------
# СОЗДАНИЕ ТАБЛИЦ ПРИ ЗАПУСКЕ
# ----------------------------------------------------------------------
with app.app_context():
    db.create_all()


# ----------------------------------------------------------------------
# ЗАПУСК
# ----------------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True)
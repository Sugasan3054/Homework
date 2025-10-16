# -*- coding: utf-8 -*-
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------
# 初期設定
# ---------------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a_very_secret_key_that_should_be_changed')

# データベース設定
db_uri = os.environ.get('DATABASE_URL')
# RenderのPostgreSQL URLは 'postgres://' で始まるため、'postgresql://' に置換
if db_uri and db_uri.startswith("postgres://"):
    db_uri = db_uri.replace("postgres://", "postgresql://", 1)

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = db_uri or 'sqlite:///' + os.path.join(basedir, 'blog.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "このページにアクセスするにはログインが必要です。"

# ---------------------------------
# データベースモデル定義
# (変更なし)
# ---------------------------------

# Userテーブル
class User(UserMixin, db.Model):
    __tablename__ = 'User'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    articles = db.relationship('Article', backref='author', lazy=True, cascade="all, delete-orphan")
    comments = db.relationship('Comment', backref='commenter', lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Articleテーブル
class Article(db.Model):
    __tablename__ = 'Article'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('User.id'), nullable=False)
    comments = db.relationship('Comment', backref='article_ref', lazy=True, cascade="all, delete-orphan")

# Commentテーブル
class Comment(db.Model):
    __tablename__ = 'Comment'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('User.id'), nullable=False)
    article_id = db.Column(db.Integer, db.ForeignKey('Article.id'), nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------------------------------
# ルーティング
# (変更なし)
# ---------------------------------

# 記事一覧表示 (トップページ)
@app.route('/')
def index():
    articles = Article.query.order_by(Article.date_posted.desc()).all()
    return render_template('index.html', articles=articles)

# ログイン・ユーザ登録ページ
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and user.check_password(request.form['password']):
            login_user(user, remember=True)
            flash('ログインしました。', 'success')
            return redirect(url_for('index'))
        else:
            flash('メールアドレスまたはパスワードが正しくありません。', 'danger')
    return render_template('login.html')

# ユーザ登録処理
@app.route('/register', methods=['POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    username = request.form['username']
    email = request.form['email']
    password = request.form['password']

    if User.query.filter_by(username=username).first():
        flash('このユーザ名は既に使用されています。', 'danger')
        return redirect(url_for('login'))
    if User.query.filter_by(email=email).first():
        flash('このメールアドレスは既に使用されています。', 'danger')
        return redirect(url_for('login'))

    new_user = User(username=username, email=email)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    
    flash('ユーザ登録が完了しました。ログインしてください。', 'success')
    return redirect(url_for('login'))

# ログアウト処理
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('ログアウトしました。', 'info')
    return redirect(url_for('index'))

# 記事詳細・コメント投稿
@app.route('/article/<int:article_id>')
def article(article_id):
    target_article = Article.query.get_or_404(article_id)
    return render_template('article.html', article=target_article)

# 記事投稿
@app.route('/new_article', methods=['GET', 'POST'])
@login_required
def new_article():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        
        if not title or not content:
            flash('タイトルと本文を入力してください。', 'danger')
            return render_template('edit_article.html', article=None)

        new_article = Article(title=title, content=content, author=current_user)
        db.session.add(new_article)
        db.session.commit()
        flash('新しい記事が投稿されました。', 'success')
        return redirect(url_for('index'))
        
    return render_template('edit_article.html', article=None)

# 記事編集
@app.route('/edit_article/<int:article_id>', methods=['GET', 'POST'])
@login_required
def edit_article(article_id):
    article_to_edit = Article.query.get_or_404(article_id)
    if article_to_edit.author != current_user:
        abort(403) # 編集権限がない場合は403エラー

    if request.method == 'POST':
        article_to_edit.title = request.form['title']
        article_to_edit.content = request.form['content']
        db.session.commit()
        flash('記事が更新されました。', 'success')
        return redirect(url_for('article', article_id=article_to_edit.id))
        
    return render_template('edit_article.html', article=article_to_edit)

# 記事削除
@app.route('/delete_article/<int:article_id>', methods=['POST'])
@login_required
def delete_article(article_id):
    article_to_delete = Article.query.get_or_404(article_id)
    if article_to_delete.author != current_user:
        abort(403)
        
    db.session.delete(article_to_delete)
    db.session.commit()
    flash('記事を削除しました。', 'info')
    return redirect(url_for('index'))

# コメント投稿
@app.route('/add_comment/<int:article_id>', methods=['POST'])
@login_required
def add_comment(article_id):
    article_to_comment = Article.query.get_or_404(article_id)
    content = request.form['content']

    if not content:
        flash('コメント内容を入力してください。', 'danger')
        return redirect(url_for('article', article_id=article_id))

    new_comment = Comment(content=content, commenter=current_user, article_ref=article_to_comment)
    db.session.add(new_comment)
    db.session.commit()
    flash('コメントを投稿しました。', 'success')
    return redirect(url_for('article', article_id=article_id))

# ---------------------------------
# データベース初期化
# ---------------------------------
# アプリケーションコンテキスト内でテーブルを作成
with app.app_context():
    db.create_all()
    
# ローカル開発用のDB初期化コマンド
@app.cli.command('init-db')
def init_db_command():
    """データベーステーブルを再作成します。"""
    db.drop_all()
    db.create_all()
    print('データベースを再作成しました。')

# 以下のブロックは本番環境では不要なため削除またはコメントアウトします。
# if __name__ == '__main__':
#     app.run(debug=True)


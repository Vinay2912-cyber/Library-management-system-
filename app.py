from flask import Flask, g, render_template, request, redirect, url_for, flash
import sqlite3
import os
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(__file__)
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
DB_PATH = os.path.join(INSTANCE_DIR, 'library.db')

if not os.path.exists(INSTANCE_DIR):
    os.makedirs(INSTANCE_DIR)

app = Flask(__name__)
app.config['DATABASE'] = DB_PATH
app.secret_key = 'replace-this-with-a-secure-random-key'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['DATABASE'])
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON;')
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.route('/')
def index():
    q = request.args.get('q', '').strip()
    db = get_db()
    if q:
        sql = "SELECT * FROM books WHERE title LIKE ? OR author LIKE ? OR isbn LIKE ?"
        term = f"%{q}%"
        books = db.execute(sql, (term, term, term)).fetchall()
    else:
        books = db.execute('SELECT * FROM books ORDER BY title').fetchall()

    return render_template('index.html', books=books, q=q)

@app.route('/book/add', methods=['GET', 'POST'])
def add_book():
    if request.method == 'POST':
        title = request.form['title'].strip()
        author = request.form['author'].strip()
        isbn = request.form['isbn'].strip() or None
        copies = request.form.get('copies', '1')

        if not title or not author:
            flash('Title and Author are required.', 'danger')
            return redirect(url_for('add_book'))

        try:
            copies_i = int(copies)
            if copies_i < 1:
                raise ValueError
        except ValueError:
            flash('Copies must be a positive integer.', 'danger')
            return redirect(url_for('add_book'))

        db = get_db()
        try:
            db.execute('INSERT INTO books (title, author, isbn, copies, available) VALUES (?, ?, ?, ?, ?)',
                       (title, author, isbn, copies_i, copies_i))
            db.commit()
            flash('Book added successfully.', 'success')
            return redirect(url_for('index'))
        except sqlite3.IntegrityError:
            flash('ISBN must be unique. A book with this ISBN already exists.', 'danger')
            return redirect(url_for('add_book'))

    return render_template('add_book.html')

@app.route('/book/edit/<int:book_id>', methods=['GET', 'POST'])
def edit_book(book_id):
    db = get_db()
    book = db.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()
    if not book:
        flash('Book not found.', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form['title'].strip()
        author = request.form['author'].strip()
        isbn = request.form['isbn'].strip() or None
        copies = request.form.get('copies', '1')

        try:
            copies_i = int(copies)
            if copies_i < 1:
                raise ValueError
        except ValueError:
            flash('Copies must be a positive integer.', 'danger')
            return redirect(url_for('edit_book', book_id=book_id))

        delta = copies_i - book['copies']
        new_available = book['available'] + delta
        if new_available < 0:
            flash('Cannot reduce copies below currently issued number.', 'danger')
            return redirect(url_for('edit_book', book_id=book_id))

        try:
            db.execute('UPDATE books SET title=?, author=?, isbn=?, copies=?, available=? WHERE id=?',
                       (title, author, isbn, copies_i, new_available, book_id))
            db.commit()
            flash('Book updated.', 'success')
            return redirect(url_for('index'))
        except sqlite3.IntegrityError:
            flash('ISBN must be unique.', 'danger')
            return redirect(url_for('edit_book', book_id=book_id))

    return render_template('edit_book.html', book=book)

@app.route('/book/delete/<int:book_id>', methods=['POST'])
def delete_book(book_id):
    db = get_db()
    db.execute('DELETE FROM books WHERE id=?', (book_id,))
    db.commit()
    flash('Book deleted (if existed).', 'success')
    return redirect(url_for('index'))

@app.route('/issue/<int:book_id>', methods=['GET', 'POST'])
def issue_book(book_id):
    db = get_db()
    book = db.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()
    if not book:
        flash('Book not found.', 'danger')
        return redirect(url_for('index'))

    if book['available'] < 1:
        flash('No copies available to issue.', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        name = request.form['name'].strip()
        sclass = request.form.get('class', '').strip()
        contact = request.form.get('contact', '').strip()
        days = request.form.get('days', '14')

        if not name:
            flash('Borrower name is required.', 'danger')
            return redirect(url_for('issue_book', book_id=book_id))

        try:
            days_i = int(days)
            if days_i < 1:
                raise ValueError
        except ValueError:
            flash('Days must be a positive integer.', 'danger')
            return redirect(url_for('issue_book', book_id=book_id))

        cur = db.execute('SELECT * FROM borrowers WHERE name=? AND contact=?', (name, contact))
        borrower = cur.fetchone()
        if borrower:
            borrower_id = borrower['id']
        else:
            res = db.execute('INSERT INTO borrowers (name, class, contact) VALUES (?, ?, ?)',
                             (name, sclass, contact))
            borrower_id = res.lastrowid

        issue_date = datetime.now().date()
        due_date = issue_date + timedelta(days=days_i)

        db.execute('INSERT INTO issues (book_id, borrower_id, issue_date, due_date) VALUES (?, ?, ?, ?)',
                   (book_id, borrower_id, issue_date.isoformat(), due_date.isoformat()))

        db.execute('UPDATE books SET available=available-1 WHERE id=?', (book_id,))
        db.commit()
        flash('Book issued successfully.', 'success')
        return redirect(url_for('index'))

    return render_template('issue_book.html', book=book)

@app.route('/return/<int:issue_id>', methods=['POST'])
def return_book(issue_id):
    db = get_db()
    issue = db.execute('SELECT * FROM issues WHERE id=? AND return_date IS NULL', (issue_id,)).fetchone()
    if not issue:
        flash('Issue record not found or already returned.', 'danger')
        return redirect(url_for('borrowers'))

    return_date = datetime.now().date().isoformat()
    db.execute('UPDATE issues SET return_date=? WHERE id=?', (return_date, issue_id))
    db.execute('UPDATE books SET available=available+1 WHERE id=?', (issue['book_id'],))
    db.commit()
    flash('Book returned successfully.', 'success')
    return redirect(url_for('borrowers'))

@app.route('/borrowers')
def borrowers():
    db = get_db()
    rows = db.execute('''
        SELECT issues.id AS issue_id, books.title, borrowers.name, borrowers.class, issues.issue_date, issues.due_date, issues.return_date
        FROM issues
        JOIN books ON books.id = issues.book_id
        JOIN borrowers ON borrowers.id = issues.borrower_id
        ORDER BY issues.issue_date DESC
    ''').fetchall()
    return render_template('borrowers.html', rows=rows)

if __name__ == '__main__':
    if not os.path.exists(app.config['DATABASE']):
        print('Database not found — initializing using schema.sql')
        import subprocess
        subprocess.run([sys.executable, 'init_db.py'])
    app.run(debug=True)

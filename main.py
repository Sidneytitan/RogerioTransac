from flask import Flask, render_template


app = Flask(__name__)



@app.route('/')
def estoque():
    return render_template('estoque.html')

if __name__ == '__main__':
    app.run(debug=True)
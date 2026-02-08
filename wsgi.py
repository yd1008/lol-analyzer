from app import create_app

app = create_app('production')

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    from waitress import serve
    serve(app, host='0.0.0.0', port=port)

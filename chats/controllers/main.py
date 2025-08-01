@app.route('/')
def index():
    return render_template('handover_asisstant/dashboard.html')

@app.route('/chat', methods=['POST'])
async def chat():
    data = request.get_json()
    message = data.get('message')
    if not message:
        return jsonify({'error': 'No message provided'}), 400
    # Pastikan terhubung
    if not mcp_client.is_connected():
        await connect_mcp()
    # Proses query
    response = await mcp_client.process_query(message)
    return jsonify({'response': response})

@app.route('/upload', methods=['POST'])
async def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['file']
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(save_path)
        # Panggil tool MCP untuk ingestor dokumen
        args = {
            'filename': filename,
            'pelanggan': request.form.get('pelanggan'),
            'project': request.form.get('project'),
            'tahun': request.form.get('tahun')
        }
        try:
            result = await mcp_client.call_tool('add_kak_tor_knowledge', args)
            return jsonify({'status': 'success', 'ingest': result})
        except Exception as e:
            logger.error(f'Ingest error: {e}')
            return jsonify({'error': str(e)}), 500
    else:
        return jsonify({'error': 'Invalid file type'}), 400

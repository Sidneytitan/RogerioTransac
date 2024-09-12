from flask import Flask, render_template, request, redirect, url_for, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
import datetime

app = Flask(__name__)

# Conexão com o MongoDB
def connect_to_mongodb():
    try:
        client = MongoClient("mongodb+srv://sidneycko:titanbetty@cluster0.feenv6t.mongodb.net/?retryWrites=true&w=majority")
        db = client["transac"]
        collection_pedido = db["pedido"]
        collection_estoque = db["produtos"]
        return collection_pedido, collection_estoque, db
    except Exception as e:
        print(f"Erro ao conectar ao MongoDB: {e}")
        return None, None, None

# Formatação de data
def format_datetime(date_value):
    if isinstance(date_value, datetime.datetime):
        return date_value.strftime("%Y-%m-%d %H:%M")
    return date_value

# Página principal - Gerenciamento de pedidos
@app.route('/', methods=['GET', 'POST'])
def index():
    collection_pedido, _, _ = connect_to_mongodb()
    if collection_pedido is None:
        return "Erro de conexão com MongoDB. Verifique o log para mais detalhes."

    if request.method == 'POST':
        pedido_id = request.form.get('pedido_id')
        obs = request.form.get('observacao')
        boleto_enviado = request.form.get('boleto_enviado')

        update_data = {}
        if obs is not None and obs.strip() != "":
            update_data['Obs:'] = obs
        if boleto_enviado:
            update_data['Boleto Enviado'] = boleto_enviado

        if update_data:
            try:
                collection_pedido.update_one({'_id': ObjectId(pedido_id)}, {'$set': update_data})
            except Exception as e:
                print(f"Erro ao atualizar pedido: {e}")

        return redirect(url_for('index'))

    try:
        search_query = request.args.get('search')
        if search_query:
            try:
                search_query = int(search_query)
                pedidos = list(collection_pedido.find({'ID Pedido': search_query}))
            except ValueError:
                pedidos = []
        else:
            pedidos = list(collection_pedido.find())

        for pedido in pedidos:
            pedido['Data de Emissão'] = format_datetime(pedido.get('Data de Emissão'))
            pedido['Vencimento'] = format_datetime(pedido.get('Vencimento'))
            pedido['Data de Finalização'] = format_datetime(pedido.get('Data de Finalização'))

        filiais = ['Paulínia', 'Barueri', 'Uberlandia', 'SEN CANEDO']
        pedidos_por_filial = {filial: 0 for filial in filiais}
        pedidos_por_filial_boleto = {filial: {'Sim': 0, 'Não': 0} for filial in filiais}
        total_boleto_sim = 0
        total_boleto_nao = 0

        for pedido in pedidos:
            filial = pedido.get('Filial')
            if filial in pedidos_por_filial:
                pedidos_por_filial[filial] += 1
                boleto_status = pedido.get('Boleto Enviado', 'Não')
                if boleto_status == 'Sim':
                    total_boleto_sim += 1
                elif boleto_status == 'Não':
                    total_boleto_nao += 1
                if boleto_status not in ['Sim', 'Não']:
                    boleto_status = 'Não'
                pedidos_por_filial_boleto[filial][boleto_status] += 1

        total_pedidos = sum(pedidos_por_filial.values())
        return render_template('pedido.html', pedidos=pedidos, pedidos_por_filial=pedidos_por_filial,
                               pedidos_por_filial_boleto=pedidos_por_filial_boleto, total_pedidos=total_pedidos,
                               total_boleto_sim=total_boleto_sim, total_boleto_nao=total_boleto_nao)
    except Exception as e:
        return f"Erro ao ler dados do MongoDB: {e}"

# Página de Estoque com Filtro por Filial
@app.route('/estoque', methods=['GET'])
def estoque():
    _, collection_estoque, db = connect_to_mongodb()
    if collection_estoque is None:
        return "Erro de conexão com MongoDB. Verifique o log para mais detalhes."

    # Obter o parâmetro da filial selecionada
    filial_selecionada = request.args.get('filial', 'Todas')

    # Filtrar histórico de acordo com a filial selecionada
    if filial_selecionada == 'Todas':
        historico_cursor = db.historico.find()
    else:
        historico_cursor = db.historico.find({'filial': filial_selecionada})

    historico = list(historico_cursor)

    # Calcular a quantidade total e o valor total usando o histórico
    quantidade_total = 0
    valor_total = 0.0

    # Dicionário para armazenar a quantidade total de cada produto
    quantidade_por_produto = {}

    for item in historico:
        produto_id = item['produto_id']
        if item['acao'].lower() == 'entrada':
            quantidade_por_produto[produto_id] = quantidade_por_produto.get(produto_id, 0) + item['quantidade']
            valor_total += item['quantidade'] * item['valor_unitario']
        elif item['acao'].lower() == 'saida':
            quantidade_por_produto[produto_id] = quantidade_por_produto.get(produto_id, 0) - item['quantidade']
            valor_total -= item['quantidade'] * item['valor_unitario']

    # Calcular a quantidade total considerando todos os produtos
    quantidade_total = sum(quantidade_por_produto.values())

    # Obter os produtos correspondentes à filial selecionada
    if filial_selecionada == 'Todas':
        produtos = list(collection_estoque.find())
    else:
        produtos = list(collection_estoque.find({'filial': filial_selecionada}))

    # Atualizar cada produto com a quantidade total calculada
    for produto in produtos:
        produto_id = produto['produto_id']
        produto['quantidade'] = quantidade_por_produto.get(produto_id, 0)

    # Lista de todas as filiais para o filtro
    filiais = collection_estoque.distinct('filial')

    return render_template('estoque.html', produtos=produtos, quantidade_total=quantidade_total, valor_total=valor_total, filiais=filiais, filial_selecionada=filial_selecionada)

@app.route('/processar_estoque', methods=['POST'])
def processar_estoque():
    _, collection_estoque, db = connect_to_mongodb()
    if collection_estoque is None:
        return "Erro de conexão com MongoDB. Verifique o log para mais detalhes."

    produto_id = request.form['produto_id']
    quantidade = request.form.get('quantidade', '0')
    acao = request.form['acao']
    valor_unitario = request.form.get('valor_unitario', '0')
    valor_total = request.form.get('valor_total', '0')
    filial = request.form.get('filial', '')
    quem_lancando = request.form.get('quem_lancando', '')  # Novo campo para "Quem está lançando"
    observacoes = request.form.get('observacoes', '')

    # Converte valores para float ou int, garantindo que valores vazios sejam tratados como 0
    try:
        quantidade = int(quantidade) if quantidade else 0
        valor_unitario = float(valor_unitario) if valor_unitario else 0.0
        valor_total = float(valor_total) if valor_total else 0.0
    except ValueError:
        quantidade = 0
        valor_unitario = 0.0
        valor_total = 0.0

    data_entrada = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Atualizar estoque e garantir que o produto já exista
    if acao == 'entrada':
        collection_estoque.update_one(
            {'produto_id': produto_id},
            {'$inc': {'quantidade': quantidade}},
            upsert=False  # Não criar um novo documento, deve falhar se não encontrar o produto
        )
    elif acao == 'saida':
        collection_estoque.update_one(
            {'produto_id': produto_id},
            {'$inc': {'quantidade': -quantidade}},
            upsert=False  # Não criar um novo documento, deve falhar se não encontrar o produto
        )

    # Registrar a operação no histórico do produto
    historico = {
        'produto_id': produto_id,
        'quantidade': quantidade,
        'acao': acao,
        'valor_unitario': valor_unitario,
        'valor_total': valor_total,
        'filial': filial,
        'quem_lancando': quem_lancando,  # Salvar quem está lançando
        'data': data_entrada,
        'observacoes': observacoes,
    }
    db.historico.insert_one(historico)

    return redirect(url_for('estoque'))

@app.route('/cadastrar_produto', methods=['POST'])
def cadastrar_produto():
    _, collection_estoque, _ = connect_to_mongodb()
    if collection_estoque is None:
        return "Erro de conexão com MongoDB. Verifique o log para mais detalhes."

    produto_id = request.form['produto_id']
    produto_nome = request.form['produto_nome']
    produto_tipo = request.form['produto_tipo']

    # Verifica se o produto já existe no estoque
    if not collection_estoque.find_one({'produto_id': produto_id}):
        # Insere o produto na coleção com seus detalhes
        collection_estoque.insert_one({
            'produto_id': produto_id,
            'produto_nome': produto_nome,
            'produto_tipo': produto_tipo,
            'quantidade': 0
        })

    return redirect(url_for('estoque'))

@app.route('/historico/<produto_id>', methods=['GET'])
def historico(produto_id):
    _, collection_estoque, db = connect_to_mongodb()
    if db is None:
        return "Erro de conexão com MongoDB. Verifique o log para mais detalhes."

    # Buscar o nome do produto na coleção de estoque usando o produto_id
    produto = collection_estoque.find_one({'produto_id': produto_id})
    nome_produto = produto['produto_nome'] if produto else "Nome desconhecido"

    # Obter a filial selecionada do parâmetro da consulta (ou 'Todas' por padrão)
    filial_selecionada = request.args.get('filial', 'Todas')

    # Buscar o histórico de movimentação do produto
    if filial_selecionada == 'Todas':
        historico_cursor = db.historico.find({'produto_id': produto_id})
    else:
        historico_cursor = db.historico.find({'produto_id': produto_id, 'filial': filial_selecionada})
    historico = list(historico_cursor)

    # Calcular a quantidade total e o valor total considerando entrada e saída
    quantidade_total = 0
    valor_total = 0.0

    for item in historico:
        if item['acao'].lower() == 'entrada':
            quantidade_total += item['quantidade']
            valor_total += item['quantidade'] * item['valor_unitario']
        else:  # Se for 'saida'
            quantidade_total -= item['quantidade']
            valor_total -= item['quantidade'] * item['valor_unitario']

    # Obtendo lista de filiais para o filtro
    filiais = db.historico.distinct('filial')

    return render_template('historico.html',
                           historico=historico,
                           produto_id=produto_id,
                           nome_produto=nome_produto,
                           quantidade_total=quantidade_total,
                           valor_total=valor_total,
                           filiais=filiais,
                           filial_selecionada=filial_selecionada)

@app.route('/obter_valor_unitario', methods=['GET'])
def obter_valor_unitario():
    _, _, db = connect_to_mongodb()
    if db is None:
        return jsonify({'valor_unitario': 0})

    produto_id = request.args.get('produto_id')
    ultima_entrada = list(db.historico.find({'produto_id': produto_id}).sort('data', -1).limit(1))

    # Definir o valor unitário se houver uma última entrada
    valor_unitario = ultima_entrada[0]['valor_unitario'] if ultima_entrada else 0

    return jsonify({'valor_unitario': valor_unitario})

if __name__ == '__main__':
    app.run(debug=True)
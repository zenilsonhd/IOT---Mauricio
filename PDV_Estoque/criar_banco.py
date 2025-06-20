import sqlite3

# Conecta ou cria o banco
conn = sqlite3.connect('banco.db')
cursor = conn.cursor()

# Cria tabela de produtos
cursor.execute('''
CREATE TABLE IF NOT EXISTS produtos (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nome    TEXT NOT NULL,
    preco   REAL NOT NULL,
    estoque INTEGER NOT NULL
)
''')

# Cria tabela de vendas (agora com coluna data_hora, não “data”)
cursor.execute('''
CREATE TABLE IF NOT EXISTS vendas (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora  TEXT NOT NULL,
    total      REAL NOT NULL
)
''')

# Cria tabela de itens da venda
cursor.execute('''
CREATE TABLE IF NOT EXISTS itens_venda (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    venda_id    INTEGER,
    produto_id  INTEGER,
    quantidade  INTEGER,
    subtotal    REAL,
    FOREIGN KEY (venda_id)    REFERENCES vendas(id),
    FOREIGN KEY (produto_id)  REFERENCES produtos(id)
)
''')

conn.commit()
conn.close()

print("Banco de dados criado com sucesso! (com colunas: data_hora e total em vendas)")

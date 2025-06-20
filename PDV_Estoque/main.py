import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import sqlite3
import serial
import threading
import time
import win32print
from datetime import datetime
import re

DB_PATH = 'banco.db'
PRINTER_NAME = 'HPRT MPT-II'
SERIAL_PORT = 'COM3'
BAUDRATE = 115200
peso_atual = None

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

COR_FUNDO_PRINCIPAL = "#F0F2F5"
COR_FUNDO_SECUNDARIO = "#FFFFFF"
COR_AZUL_PRIMARIO = "#4A90E2"
COR_AZUL_ESCURO = "#0D47A1"
COR_VERMELHO_ALERTA = "#D32F2F"
COR_VERDE_SUCESSO = "#388E3C"
COR_AMARELO_AVISO = "#FFA000"

def criar_tabela():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            preco REAL NOT NULL,
            estoque INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def obter_produto_por_id(produto_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome, preco, estoque FROM produtos WHERE id=?", (produto_id,))
    produto = cursor.fetchone()
    conn.close()
    return produto

def atualizar_estoque_db(produto_id, quantidade_vendida):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE produtos SET estoque = estoque - ? WHERE id=?",
        (quantidade_vendida, produto_id)
    )
    conn.commit()
    conn.close()

def imprimir_cupom_escpos_raw(venda_itens):
    ESC = b'\x1b'
    GS = b'\x1d'

    try:
        hPrinter = win32print.OpenPrinter(PRINTER_NAME)
        try:
            hJob = win32print.StartDocPrinter(hPrinter, 1, ("Cupom PDV", None, "RAW"))
            win32print.StartPagePrinter(hPrinter)

            win32print.WritePrinter(hPrinter, ESC + b'@')

            data_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            header = (
                "      MERCADO PAI E FILHO      \n"
                "Rua Santa Luzia, 09\n"
                f"{data_hora}\n"
                "------------------------------\n"
                "Itens:\n"
            )
            win32print.WritePrinter(hPrinter, header.encode('cp850'))

            total = 0.0
            for prod_id, item in venda_itens.items():
                nome = item['nome']
                qtd = item['quantidade']
                preco_unit = item['preco']
                subtotal = preco_unit * qtd
                nome_formatado = (nome[:15] + '..') if len(nome) > 17 else nome
                linha_item = f"{nome_formatado:<17} {qtd:>3} x {preco_unit:>6.2f} = {subtotal:>7.2f}\n"
                win32print.WritePrinter(hPrinter, linha_item.encode('cp850'))
                total += subtotal

            separador = "------------------------------\n"
            win32print.WritePrinter(hPrinter, separador.encode('cp850'))

            total_text = f"TOTAL: R$ {total:.2f}\n"
            win32print.WritePrinter(hPrinter, ESC + b'a' + b'\x01')
            win32print.WritePrinter(hPrinter, total_text.encode('cp850'))
            win32print.WritePrinter(hPrinter, ESC + b'a' + b'\x00')

            agradecimento = "\nObrigado pela sua compra!\nVolte sempre!\n\n"
            win32print.WritePrinter(hPrinter, ESC + b'a' + b'\x01')
            win32print.WritePrinter(hPrinter, agradecimento.encode('cp850'))
            win32print.WritePrinter(hPrinter, ESC + b'a' + b'\x00')

            win32print.WritePrinter(hPrinter, GS + b'V' + b'\x00')

            win32print.EndPagePrinter(hPrinter)
            win32print.EndDocPrinter(hPrinter)
        finally:
            win32print.ClosePrinter(hPrinter)

    except Exception as e:
        print(f"Erro ao imprimir: {e}")
        messagebox.showerror("Erro de Impressão", f"Não foi possível imprimir o cupom.\nVerifique a impressora '{PRINTER_NAME}'.\nErro: {e}")

def ler_peso_esp32():
    global peso_atual
    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1)
        print(f"Conectado ao ESP32 na {SERIAL_PORT}")
        time.sleep(2)

        while True:
            raw_line = ser.readline()
            if raw_line:
                raw = raw_line.decode('utf-8', errors='ignore').strip()
                if raw.startswith("Peso (g):"):
                    valor_str = raw.split(":")[1].strip()
                    try:
                        peso = float(valor_str)
                        if peso < 0:
                            peso = 0.0
                        peso_atual = peso
                    except ValueError:
                        pass
            time.sleep(0.1)

    except serial.SerialException as e:
        print(f"Erro: Não foi possível conectar à porta {SERIAL_PORT}. Erro: {e}")
    except Exception as e:
        print(f"Erro desconhecido na leitura serial: {e}")

threading.Thread(target=ler_peso_esp32, daemon=True).start()

class CadastroFrame(ctk.CTkFrame):
    def __init__(self, master, voltar_callback):
        super().__init__(master, fg_color=COR_FUNDO_PRINCIPAL)
        self.voltar_callback = voltar_callback
        self.produto_selecionado = None

        ctk.CTkLabel(self, text="Cadastro de Produtos",
                     font=ctk.CTkFont("Segoe UI", 32, "bold"),
                     text_color=COR_AZUL_ESCURO).pack(pady=25)

        frame_form = ctk.CTkFrame(self, fg_color=COR_FUNDO_SECUNDARIO, corner_radius=10)
        frame_form.pack(pady=15, padx=30, fill="x") 
        frame_form.grid_columnconfigure(1, weight=1)

        labels_info = [
            ("Nome:", "nome_entry"),
            ("Preço (R$):", "preco_entry"),
            ("Estoque:", "estoque_entry")
        ]

        for i, (label_text, entry_attr_name) in enumerate(labels_info):
            ctk.CTkLabel(frame_form, text=label_text, fg_color=COR_FUNDO_SECUNDARIO,
                         text_color="black", font=ctk.CTkFont("Segoe UI", 16))\
                .grid(row=i, column=0, pady=8, sticky='e', padx=(20, 10))
            entry = ctk.CTkEntry(frame_form, font=ctk.CTkFont("Segoe UI", 16), width=350, height=38)
            entry.grid(row=i, column=1, pady=8, padx=(0, 20), sticky='ew')
            setattr(self, entry_attr_name, entry)

        frame_botoes = ctk.CTkFrame(self, fg_color=COR_FUNDO_PRINCIPAL)
        frame_botoes.pack(pady=15)

        button_configs = [
            ("Cadastrar", self.cadastrar_produto, COR_AZUL_PRIMARIO),
            ("Atualizar Lista", self.listar_produtos, COR_AZUL_PRIMARIO),
            ("Editar Produto", self.editar_produto, COR_AMARELO_AVISO),
            ("Excluir Produto", self.excluir_produto, COR_VERMELHO_ALERTA),
        ]

        for i, (text, cmd, color) in enumerate(button_configs):
            ctk.CTkButton(frame_botoes, text=text, command=cmd,
                          fg_color=color, text_color="white",
                          font=ctk.CTkFont("Segoe UI", 14), width=180, height=45,
                          hover_color=COR_AZUL_ESCURO if color == COR_AZUL_PRIMARIO else (COR_VERDE_SUCESSO if color == COR_VERDE_SUCESSO else (COR_AMARELO_AVISO if color == COR_AMARELO_AVISO else None)))\
                .grid(row=0, column=i, padx=8)

        ctk.CTkButton(self, text="Voltar ao Menu Principal",
                      command=self.voltar_callback,
                      fg_color=COR_VERMELHO_ALERTA, text_color="white",
                      font=ctk.CTkFont("Segoe UI", 14), width=220, height=45)\
            .pack(pady=25)

        ctk.CTkLabel(self, text="Produtos Cadastrados",
                     font=ctk.CTkFont("Segoe UI", 22, "bold"),
                     text_color=COR_AZUL_ESCURO).pack(pady=15)

        listbox_wrapper_frame = ctk.CTkFrame(self, fg_color=COR_FUNDO_SECUNDARIO, corner_radius=10, border_color=COR_AZUL_PRIMARIO, border_width=2)
        listbox_wrapper_frame.pack(pady=10, padx=30, fill="both", expand=True)

        self.tk_listbox = tk.Listbox(listbox_wrapper_frame, width=90, height=15,
                                     font=("Consolas", 12),
                                     bg=COR_FUNDO_SECUNDARIO, fg="black",
                                     selectbackground=COR_AZUL_PRIMARIO, selectforeground="white",
                                     borderwidth=0, highlightthickness=0)
        self.tk_listbox.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        scrollbar = ctk.CTkScrollbar(listbox_wrapper_frame, command=self.tk_listbox.yview,
                                     button_color=COR_AZUL_PRIMARIO, button_hover_color=COR_AZUL_ESCURO)
        scrollbar.pack(side="right", fill="y")
        self.tk_listbox.config(yscrollcommand=scrollbar.set)

        self.tk_listbox.bind('<<ListboxSelect>>', self.selecionar_produto)

        self.label_estoque_baixo = ctk.CTkLabel(self, text="",
                                                 font=ctk.CTkFont("Segoe UI", 14, "bold"),
                                                 text_color=COR_VERMELHO_ALERTA)
        self.label_estoque_baixo.pack(pady=10)

        self.listar_produtos()
        self.atualizar_aviso_estoque()

    def validar_entradas_numericas(self, preco_str, estoque_str):
        try:
            preco = float(preco_str.replace(',', '.'))
        except ValueError:
            messagebox.showerror("Erro de Entrada", "Preço deve ser um número válido (ex: 10.50 ou 10,50).")
            return None, None
        
        try:
            estoque = int(estoque_str)
        except ValueError:
            messagebox.showerror("Erro de Entrada", "Estoque deve ser um número inteiro válido.")
            return None, None
        
        if preco < 0 or estoque < 0:
            messagebox.showwarning("Valor Inválido", "Preço e estoque não podem ser negativos.")
            return None, None
            
        return preco, estoque

    def cadastrar_produto(self):
        nome = self.nome_entry.get().strip()
        preco_str = self.preco_entry.get().strip()
        estoque_str = self.estoque_entry.get().strip()

        if not nome:
            messagebox.showwarning("Atenção", "Nome do produto não pode estar vazio.")
            return

        preco, estoque = self.validar_entradas_numericas(preco_str, estoque_str)
        if preco is None or estoque is None:
            return

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO produtos (nome, preco, estoque) VALUES (?, ?, ?)",
                           (nome, preco, estoque))
            conn.commit()
            messagebox.showinfo("Sucesso", f"Produto '{nome}' cadastrado com sucesso!")
            self.limpar_campos()
            self.listar_produtos()
        except sqlite3.Error as e:
            messagebox.showerror("Erro no Banco de Dados", f"Não foi possível cadastrar o produto: {e}")
        finally:
            conn.close()

    def listar_produtos(self):
        self.tk_listbox.delete(0, tk.END)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, preco, estoque FROM produtos ORDER BY nome ASC")
        produtos = cursor.fetchall()
        conn.close()

        for p in produtos:
            self.tk_listbox.insert(
                tk.END,
                f"ID:{p[0]:<4} | {p[1]:<30} | R$ {p[2]:<10.2f} | Estoque: {p[3]:<5}"
            )

    def selecionar_produto(self, event):
        selection = self.tk_listbox.curselection()
        if not selection:
            return

        linha_selecionada = self.tk_listbox.get(selection[0])
        match = re.match(r"ID:(\d+)", linha_selecionada)
        if not match:
            messagebox.showerror("Erro de Seleção", "Formato de item da lista inválido. Por favor, selecione um item válido.")
            self.produto_selecionado = None
            return

        prod_id = int(match.group(1))
        produto = obter_produto_por_id(prod_id)

        if produto:
            self.limpar_campos()
            self.nome_entry.insert(0, produto[1])
            self.preco_entry.insert(0, str(produto[2]))
            self.estoque_entry.insert(0, str(produto[3]))
            self.produto_selecionado = produto[0]
        else:
            messagebox.showwarning("Produto Não Encontrado", "O produto selecionado não foi encontrado no banco de dados.")
            self.limpar_campos()

    def editar_produto(self):
        if self.produto_selecionado is None:
            messagebox.showwarning("Atenção", "Nenhum produto selecionado para editar.")
            return

        nome = self.nome_entry.get().strip()
        preco_str = self.preco_entry.get().strip()
        estoque_str = self.estoque_entry.get().strip()

        if not nome:
            messagebox.showwarning("Atenção", "Nome do produto não pode estar vazio.")
            return

        preco, estoque = self.validar_entradas_numericas(preco_str, estoque_str)
        if preco is None or estoque is None:
            return

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE produtos SET nome=?, preco=?, estoque=? WHERE id=?",
                (nome, preco, estoque, self.produto_selecionado)
            )
            conn.commit()
            messagebox.showinfo("Sucesso", f"Produto '{nome}' atualizado com sucesso!")
            self.limpar_campos()
            self.listar_produtos()
        except sqlite3.Error as e:
            messagebox.showerror("Erro no Banco de Dados", f"Não foi possível atualizar o produto: {e}")
        finally:
            conn.close()

    def excluir_produto(self):
        if self.produto_selecionado is None:
            messagebox.showwarning("Atenção", "Nenhum produto selecionado para excluir.")
            return

        produto_nome = self.nome_entry.get().strip()
        confirmar = messagebox.askyesno("Confirmação de Exclusão",
                                         f"Deseja realmente excluir o produto '{produto_nome}' (ID: {self.produto_selecionado})?")
        if not confirmar:
            return

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM produtos WHERE id=?", (self.produto_selecionado,))
            conn.commit()
            messagebox.showinfo("Sucesso", "Produto excluído com sucesso!")
            self.limpar_campos()
            self.listar_produtos()
        except sqlite3.Error as e:
            messagebox.showerror("Erro no Banco de Dados", f"Não foi possível excluir o produto: {e}")
        finally:
            conn.close()

    def limpar_campos(self):
        self.nome_entry.delete(0, tk.END)
        self.preco_entry.delete(0, tk.END)
        self.estoque_entry.delete(0, tk.END)
        self.produto_selecionado = None

    def atualizar_aviso_estoque(self):
        global peso_atual
        if peso_atual is not None and peso_atual < 100:
            texto = f"⚠️ Atenção: Estoque físico na balança baixo! Peso detectado: {peso_atual:.2f} g"
            self.label_estoque_baixo.configure(text=texto, text_color=COR_VERMELHO_ALERTA)
        else:
            self.label_estoque_baixo.configure(text="", text_color=COR_VERMELHO_ALERTA)
        self.after(1000, self.atualizar_aviso_estoque)

class VendasFrame(ctk.CTkFrame):
    def __init__(self, master, voltar_callback):
        super().__init__(master, fg_color=COR_FUNDO_PRINCIPAL)
        self.voltar_callback = voltar_callback

        self.carrinho = {}
        self.produtos_cache = {}

        ctk.CTkLabel(self, text="Tela de Vendas",
                     font=ctk.CTkFont("Segoe UI", 32, "bold"),
                     text_color=COR_AZUL_ESCURO).pack(pady=25)

        self.label_aviso_estoque_balanca = ctk.CTkLabel(self, text="",
                                                         font=ctk.CTkFont("Segoe UI", 14, "bold"),
                                                         text_color=COR_VERMELHO_ALERTA)
        self.label_aviso_estoque_balanca.pack(pady=5)

        main_layout_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_layout_frame.pack(pady=100, padx=100, fill="both", expand=True)
        main_layout_frame.grid_columnconfigure(0, weight=3) 
        main_layout_frame.grid_columnconfigure(1, weight=1) 
        main_layout_frame.grid_rowconfigure(0, weight=1)

        products_column_frame = ctk.CTkFrame(main_layout_frame, fg_color=COR_FUNDO_PRINCIPAL)
        products_column_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        products_column_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(products_column_frame, text="Selecione o Produto",
                     fg_color=COR_FUNDO_PRINCIPAL, text_color=COR_AZUL_ESCURO,
                     font=ctk.CTkFont("Segoe UI", 38, "bold"))\
            .grid(row=0, column=0, columnspan=3, pady=10, padx=10)

        self.scrollable_products_frame = ctk.CTkScrollableFrame(products_column_frame, fg_color=COR_FUNDO_SECUNDARIO, corner_radius=10)
        self.scrollable_products_frame.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=5, pady=5)
        
        for i in range(3):
            self.scrollable_products_frame.grid_columnconfigure(i, weight=1)

        self.product_buttons = {}

        cart_column_frame = ctk.CTkFrame(main_layout_frame, fg_color=COR_FUNDO_PRINCIPAL)
        cart_column_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        cart_column_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(cart_column_frame, text="Carrinho de Compras",
                     fg_color=COR_FUNDO_PRINCIPAL, text_color=COR_AZUL_ESCURO,
                     font=ctk.CTkFont("Segoe UI", 18, "bold"))\
            .grid(row=0, column=0, pady=10, padx=10)

        listbox_carrinho_wrapper = ctk.CTkFrame(cart_column_frame, fg_color=COR_FUNDO_SECUNDARIO, corner_radius=15, border_color=COR_AZUL_PRIMARIO, border_width=2)
        listbox_carrinho_wrapper.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        self.listbox_carrinho = tk.Listbox(listbox_carrinho_wrapper,
                                            font=("Consolas", 12),
                                            bg=COR_FUNDO_SECUNDARIO, fg="black",
                                            selectbackground=COR_AZUL_PRIMARIO, selectforeground="white",
                                            borderwidth=0, highlightthickness=0, relief="flat",
                                            width=60) # Largura aumentada
        self.listbox_carrinho.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        scrollbar_carrinho = ctk.CTkScrollbar(listbox_carrinho_wrapper, command=self.listbox_carrinho.yview,
                                              button_color=COR_AZUL_PRIMARIO, button_hover_color=COR_AZUL_ESCURO)
        scrollbar_carrinho.pack(side="right", fill="y")
        self.listbox_carrinho.config(yscrollcommand=scrollbar_carrinho.set)

        self.label_subtotal = ctk.CTkLabel(self, text="Subtotal: R$ 0.00",
                                             font=ctk.CTkFont("Segoe UI", 24, "bold"),
                                             text_color=COR_AZUL_ESCURO)
        self.label_subtotal.pack(pady=20)

        frame_botoes_carrinho = ctk.CTkFrame(self, fg_color=COR_FUNDO_PRINCIPAL)
        frame_botoes_carrinho.pack(pady=15)

        button_configs_vendas = [
            ("Remover Item", self.remover_carrinho, COR_VERMELHO_ALERTA),
            ("Finalizar Venda", self.finalizar_venda, COR_VERDE_SUCESSO),
        ]

        for i, (text, cmd, color) in enumerate(button_configs_vendas):
            ctk.CTkButton(frame_botoes_carrinho, text=text, command=cmd,
                          fg_color=color, text_color="white",
                          font=ctk.CTkFont("Segoe UI", 16), width=220, height=50,
                          hover_color=COR_AZUL_ESCURO if color == COR_AZUL_PRIMARIO else (COR_VERDE_SUCESSO if color == COR_VERDE_SUCESSO else (COR_VERMELHO_ALERTA if color == COR_VERMELHO_ALERTA else None)))\
                .grid(row=0, column=i, padx=10)

        ctk.CTkButton(self, text="Voltar ao Menu Principal",
                      command=self.voltar_callback,
                      fg_color=COR_VERMELHO_ALERTA, text_color="white",
                      font=ctk.CTkFont("Segoe UI", 14), width=220, height=45)\
            .pack(pady=25)

        self.carregar_produtos()
        self.atualizar_peso_balanca_aviso()
        self.atualizar_subtotal_label()

    def atualizar_peso_balanca_aviso(self):
        global peso_atual
        if peso_atual is not None and peso_atual < 100:
            self.label_aviso_estoque_balanca.configure(text="⚠️ Atenção: Estoque físico com peso baixo! Últimas unidades!", text_color=COR_VERMELHO_ALERTA)
        else:
            self.label_aviso_estoque_balanca.configure(text="", text_color=COR_VERMELHO_ALERTA)
        self.after(1000, self.atualizar_peso_balanca_aviso)

    def carregar_produtos(self):
        for widget in self.scrollable_products_frame.winfo_children():
            widget.destroy()
        self.product_buttons.clear()

        self.produtos_cache.clear()

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, preco, estoque FROM produtos ORDER BY nome ASC")
        resultados = cursor.fetchall()
        conn.close()

        row_idx, col_idx = 0, 0
        for p in resultados:
            prod_id, nome, preco, estoque = p
            self.produtos_cache[prod_id] = {"nome": nome, "preco": preco, "estoque": estoque}

            if estoque > 0:
                button = ctk.CTkButton(self.scrollable_products_frame,
                                       text=f"{nome}\nR$ {preco:.2f}\nEst: {estoque}",
                                       width=180, height=120,
                                       fg_color=COR_AZUL_PRIMARIO, text_color="white",
                                       font=ctk.CTkFont("Segoe UI", 16, "bold"),
                                       command=lambda id=prod_id: self.adicionar_carrinho(id))
                self.product_buttons[prod_id] = button
                button.grid(row=row_idx, column=col_idx, padx=10, pady=10, sticky="nsew")

                col_idx += 1
                if col_idx >= 3: 
                    col_idx = 0
                    row_idx += 1

    def adicionar_carrinho(self, prod_id):
        produto_db = obter_produto_por_id(prod_id)
        if not produto_db:
            messagebox.showerror("Erro", "Produto não encontrado no banco de dados.")
            self.carregar_produtos()
            return

        nome, preco, estoque_atual_db = produto_db[1], produto_db[2], produto_db[3]
        
        qtd_no_carrinho = self.carrinho.get(prod_id, {}).get("quantidade", 0)

        if estoque_atual_db <= qtd_no_carrinho:
            messagebox.showwarning("Estoque Insuficiente",
                                   f"Estoque insuficiente para '{nome}'.\nDisponível: {estoque_atual_db - qtd_no_carrinho} unidade(s).")
            return

        if prod_id in self.carrinho:
            self.carrinho[prod_id]["quantidade"] += 1
        else:
            self.carrinho[prod_id] = {
                "nome": nome,
                "preco": preco,
                "quantidade": 1
            }

        self.atualizar_carrinho_display()
        self.atualizar_subtotal_label()
        self.carregar_produtos()
        
        # Seleciona o item no carrinho após adicionar
        for i in range(self.listbox_carrinho.size()):
            if f"ID:{prod_id:<4}" in self.listbox_carrinho.get(i):
                self.listbox_carrinho.selection_clear(0, tk.END)
                self.listbox_carrinho.selection_set(i)
                self.listbox_carrinho.activate(i)
                self.listbox_carrinho.see(i)
                break

    def remover_carrinho(self):
        selecionado = self.listbox_carrinho.curselection()
        if not selecionado:
            messagebox.showwarning("Atenção", "Selecione um item do carrinho para remover.")
            return

        linha = self.listbox_carrinho.get(selecionado[0])
        match = re.match(r"ID:(\d+)", linha)
        if not match:
            messagebox.showerror("Erro de Seleção", "Formato de item do carrinho inválido. Selecione um item válido.")
            return
        prod_id = int(match.group(1))

        if prod_id in self.carrinho:
            self.carrinho[prod_id]["quantidade"] -= 1
            if self.carrinho[prod_id]["quantidade"] <= 0:
                del self.carrinho[prod_id]
            
            self.atualizar_carrinho_display()
            self.atualizar_subtotal_label()
            self.carregar_produtos()

            # Tenta re-selecionar o item se ainda estiver no carrinho, ou o primeiro item
            if prod_id in self.carrinho and self.listbox_carrinho.size() > 0:
                for i in range(self.listbox_carrinho.size()):
                    if f"ID:{prod_id:<4}" in self.listbox_carrinho.get(i):
                        self.listbox_carrinho.selection_set(i)
                        self.listbox_carrinho.activate(i)
                        self.listbox_carrinho.see(i)
                        break
            elif self.listbox_carrinho.size() > 0:
                self.listbox_carrinho.selection_set(0)
                self.listbox_carrinho.activate(0)
                self.listbox_carrinho.see(0)
            else:
                self.listbox_carrinho.selection_clear(0, tk.END)

    def atualizar_carrinho_display(self):
        self.listbox_carrinho.delete(0, tk.END)
        for prod_id, item in self.carrinho.items():
            subtotal = item["preco"] * item["quantidade"]
            # Trunca o nome do produto para caber na largura da listbox
            # Mantendo cerca de 25 caracteres para um bom ajuste
            nome_formatado = (item['nome'][:25] + '...') if len(item['nome']) > 25 else item['nome']
            self.listbox_carrinho.insert(
                tk.END,
                f"ID:{prod_id:<4} | {nome_formatado:<25} | Qtd: {item['quantidade']:<3} | R$ {subtotal:<7.2f}"
            )

    def calcular_subtotal(self):
        total = sum(item["preco"] * item["quantidade"] for item in self.carrinho.values())
        return total

    def atualizar_subtotal_label(self):
        subtotal = self.calcular_subtotal()
        self.label_subtotal.configure(text=f"Subtotal: R$ {subtotal:.2f}")

    def finalizar_venda(self):
        if not self.carrinho:
            messagebox.showwarning("Carrinho Vazio", "Adicione itens ao carrinho para finalizar a venda.")
            return

        total_venda = self.calcular_subtotal()
        confirmar = messagebox.askyesno("Confirmar Venda", f"Confirmar venda no valor total de R$ {total_venda:.2f}?")
        if not confirmar:
            return

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        try:
            for prod_id, item_carrinho in self.carrinho.items():
                cursor.execute("SELECT estoque FROM produtos WHERE id=?", (prod_id,))
                resultado = cursor.fetchone()
                
                if resultado is None:
                    raise ValueError(f"Produto com ID {prod_id} não encontrado no banco de dados.")
                
                estoque_disponivel = resultado[0]
                quantidade_pedida = item_carrinho["quantidade"]

                if estoque_disponivel < quantidade_pedida:
                    raise ValueError(f"Estoque insuficiente para '{item_carrinho['nome']}'. Disponível: {estoque_disponivel}.")
                
                cursor.execute(
                    "UPDATE produtos SET estoque = estoque - ? WHERE id=?",
                    (quantidade_pedida, prod_id)
                )
            
            conn.commit()
            
            try:
                imprimir_cupom_escpos_raw(self.carrinho)
                messagebox.showinfo("Sucesso", "Venda realizada e cupom impresso com sucesso!")
            except Exception as e:
                messagebox.showwarning("Venda Realizada, Impressão Falhou", f"Venda realizada com sucesso, mas houve um erro ao imprimir o cupom: {e}")

            self.carrinho.clear()
            self.atualizar_carrinho_display()
            self.atualizar_subtotal_label()
            self.carregar_produtos()

        except ValueError as ve:
            conn.rollback()
            messagebox.showwarning("Erro de Estoque", str(ve) + "\nTransação cancelada.")
        except sqlite3.Error as e:
            conn.rollback()
            messagebox.showerror("Erro no Banco de Dados", f"Não foi possível finalizar a venda: {e}")
        finally:
            conn.close()

class TelaInicial(ctk.CTkFrame):
    def __init__(self, master, mostrar_cadastro, mostrar_vendas):
        super().__init__(master, fg_color=COR_FUNDO_PRINCIPAL)
        self.mostrar_cadastro = mostrar_cadastro
        self.mostrar_vendas = mostrar_vendas

        ctk.CTkLabel(self, text="Mercado Pai e Filho",
                     font=ctk.CTkFont("Segoe UI", 50, "bold"),
                     text_color=COR_AZUL_ESCURO).pack(pady=80)

        ctk.CTkButton(self, text="Cadastro de Produtos",
                      command=self.mostrar_cadastro,
                      fg_color=COR_AZUL_PRIMARIO, text_color="white",
                      font=ctk.CTkFont("Segoe UI", 24), width=320, height=60,
                      hover_color=COR_AZUL_ESCURO)\
            .pack(pady=25)

        ctk.CTkButton(self, text="Tela de Vendas",
                      command=self.mostrar_vendas,
                      fg_color=COR_VERDE_SUCESSO, text_color="white",
                      font=ctk.CTkFont("Segoe UI", 24), width=320, height=60,
                      hover_color="#2E7D32") \
            .pack(pady=25)

        ctk.CTkLabel(self, text="Desenvolvido por Zenison José.",
                     font=ctk.CTkFont("Segoe UI", 12),
                     text_color="gray").pack(side="bottom", pady=20)

class Aplicativo(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Sistema PDV Integrado")
        self.geometry("1300x850")
        self.minsize(1100, 750)
        self.resizable(True, True)
        self.configure(fg_color=COR_FUNDO_PRINCIPAL)
        
        

        criar_tabela()

        self.tela_inicial = TelaInicial(self, self.mostrar_cadastro, self.mostrar_vendas)
        self.cadastro_frame = CadastroFrame(self, self.mostrar_tela_inicial)
        self.vendas_frame = VendasFrame(self, self.mostrar_tela_inicial)

        self.tela_inicial.pack(fill='both', expand=True)

    def mostrar_cadastro(self):
        self.vendas_frame.pack_forget()
        self.tela_inicial.pack_forget()
        self.cadastro_frame.listar_produtos()
        self.cadastro_frame.pack(fill='both', expand=True, padx=40, pady=40)

    def mostrar_vendas(self):
        self.tela_inicial.pack_forget()
        self.cadastro_frame.pack_forget()
        self.vendas_frame.carregar_produtos()
        self.vendas_frame.atualizar_carrinho_display()
        self.vendas_frame.pack(fill='both', expand=True, padx=40, pady=40)

    def mostrar_tela_inicial(self):
        self.cadastro_frame.pack_forget()
        self.vendas_frame.pack_forget()
        self.tela_inicial.pack(fill='both', expand=True)

if __name__ == "__main__":
    app = Aplicativo()
    app.mainloop()
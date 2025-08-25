import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, date
from shutil import copy2
import subprocess
import tempfile
import os

# ---------------- Conexão com banco ----------------
conn = sqlite3.connect("pdv.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS produtos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    preco REAL NOT NULL,
    estoque INTEGER NOT NULL,
    codigo_barras TEXT UNIQUE
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS vendas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_geral REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS itens_venda (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venda_id INTEGER,
    produto_id INTEGER,
    quantidade INTEGER,
    preco_unitario REAL,
    total_item REAL,
    FOREIGN KEY (venda_id) REFERENCES vendas (id),
    FOREIGN KEY (produto_id) REFERENCES produtos (id)
)
""")
conn.commit()

# ---------------- Funções Produtos ----------------
def cadastrar_produto():
    nome = entry_nome.get().strip().title()
    codigo_barras = entry_codigo_barras.get().strip()
    
    if not nome:
        messagebox.showerror("Erro", "Nome do produto é obrigatório!")
        return
        
    try:
        preco = float(entry_preco.get())
        estoque = int(entry_estoque.get())
        if preco <= 0 or estoque < 0:
            messagebox.showerror("Erro", "Preço deve ser > 0 e Estoque >= 0!")
            return
    except ValueError:
        messagebox.showerror("Erro", "Preço e estoque devem ser numéricos")
        return

    try:
        if codigo_barras:
            cursor.execute("INSERT INTO produtos (nome, preco, estoque, codigo_barras) VALUES (?, ?, ?, ?)",
                           (nome, preco, estoque, codigo_barras))
        else:
            cursor.execute("INSERT INTO produtos (nome, preco, estoque) VALUES (?, ?, ?)",
                           (nome, preco, estoque))
        
        conn.commit()
        messagebox.showinfo("Sucesso", "Produto cadastrado!")
        limpar_campos_produto()
        carregar_estoque()
        carregar_lista_produtos()
        
    except sqlite3.IntegrityError as e:
        if "nome" in str(e):
            messagebox.showerror("Erro", "Já existe um produto com este nome!")
        else:
            messagebox.showerror("Erro", "Já existe um produto com este código de barras!")

def limpar_campos_produto():
    entry_nome.delete(0, tk.END)
    entry_preco.delete(0, tk.END)
    entry_estoque.delete(0, tk.END)
    entry_codigo_barras.delete(0, tk.END)

def carregar_estoque():
    for row in tree_estoque.get_children():
        tree_estoque.delete(row)
    cursor.execute("SELECT id, nome, preco, estoque, codigo_barras FROM produtos ORDER BY nome")
    for produto in cursor.fetchall():
        tree_estoque.insert("", tk.END, values=produto)

# ---------------- Funções Vendas ----------------
carrinho = []
total_venda = 0

def carregar_lista_produtos():
    cursor.execute("SELECT nome FROM produtos ORDER BY nome")
    return [produto[0] for produto in cursor.fetchall()]

def update_sugestoes(event):
    typed = entry_produto.get().lower()
    if typed == '':
        frame_sugestoes.grid_remove()
    else:
        suggestions = [p for p in lista_produtos if typed in p.lower()]
        lista_sugestoes.delete(0, tk.END)
        for product in suggestions[:5]:
            lista_sugestoes.insert(tk.END, product)
        
        if suggestions:
            frame_sugestoes.grid()
        else:
            frame_sugestoes.grid_remove()

def hide_sugestoes(event):
    frame_sugestoes.grid_remove()

def on_produto_selected(event):
    if lista_sugestoes.curselection():
        index = lista_sugestoes.curselection()[0]
        entry_produto.delete(0, tk.END)
        entry_produto.insert(0, lista_sugestoes.get(index))
        frame_sugestoes.grid_remove()
        entry_qtd.focus()

def buscar_por_codigo():
    codigo = entry_codigo.get().strip()
    if codigo:
        cursor.execute("SELECT nome FROM produtos WHERE codigo_barras = ?", (codigo,))
        produto = cursor.fetchone()
        if produto:
            entry_produto.delete(0, tk.END)
            entry_produto.insert(0, produto[0])
            entry_qtd.focus()
        else:
            messagebox.showwarning("Não encontrado", "Código de barras não cadastrado!")

def adicionar_item():
    global total_venda
    produto_nome = entry_produto.get().strip()
    
    if not produto_nome:
        messagebox.showerror("Erro", "Digite o nome do produto!")
        return
        
    try:
        qtd = int(entry_qtd.get())
        if qtd <= 0:
            messagebox.showerror("Erro", "Quantidade deve ser maior que zero!")
            return
    except ValueError:
        messagebox.showerror("Erro", "Quantidade inválida!")
        return

    cursor.execute("SELECT id, nome, preco, estoque FROM produtos WHERE nome = ?", (produto_nome,))
    resultado = cursor.fetchone()

    if resultado:
        prod_id, nome, preco, estoque = resultado
        if estoque >= qtd:
            subtotal = preco * qtd
            total_venda += subtotal
            
            item = {
                'id': prod_id,
                'nome': nome,
                'preco': preco,
                'quantidade': qtd,
                'subtotal': subtotal
            }
            carrinho.append(item)
            
            atualizar_lista_carrinho()
            label_total.config(text=f"Total: R$ {total_venda:.2f}")
            
            entry_produto.delete(0, tk.END)
            entry_qtd.delete(0, tk.END)
            entry_produto.focus()
            
        else:
            messagebox.showwarning("Estoque", f"Estoque insuficiente! Disponível: {estoque}")
    else:
        messagebox.showerror("Erro", "Produto não encontrado!")

def atualizar_lista_carrinho():
    lista.delete(0, tk.END)
    for item in carrinho:
        lista.insert(tk.END, f"{item['nome']} x{item['quantidade']} - R$ {item['subtotal']:.2f}")

def remover_item():
    global total_venda
    if not lista.curselection():
        messagebox.showwarning("Atenção", "Selecione um item para remover!")
        return
        
    index = lista.curselection()[0]
    item_removido = carrinho.pop(index)
    total_venda -= item_removido['subtotal']
    
    atualizar_lista_carrinho()
    label_total.config(text=f"Total: R$ {total_venda:.2f}")

def finalizar_venda():
    global total_venda, carrinho
    
    if not carrinho:
        messagebox.showwarning("Atenção", "Nenhum item no carrinho!")
        return

    try:
        conn.execute("BEGIN TRANSACTION")
        
        cursor.execute("INSERT INTO vendas (total_geral) VALUES (?)", (total_venda,))
        venda_id = cursor.lastrowid
        
        for item in carrinho:
            cursor.execute("""INSERT INTO itens_venda 
                           (venda_id, produto_id, quantidade, preco_unitario, total_item) 
                           VALUES (?, ?, ?, ?, ?)""",
                           (venda_id, item['id'], item['quantidade'], item['preco'], item['subtotal']))
            
            cursor.execute("UPDATE produtos SET estoque = estoque - ? WHERE id = ?",
                           (item['quantidade'], item['id']))
        
        conn.commit()
        
        messagebox.showinfo("Sucesso", f"Venda finalizada! Total: R$ {total_venda:.2f}")
        
        # Oferece para imprimir cupom
        if messagebox.askyesno("Imprimir", "Deseja imprimir o cupom fiscal?"):
            imprimir_cupom(venda_id)
        
        carrinho = []
        total_venda = 0
        lista.delete(0, tk.END)
        label_total.config(text="Total: R$ 0.00")
        
        carregar_estoque()
        carregar_relatorios()
        
    except Exception as e:
        conn.rollback()
        messagebox.showerror("Erro", f"Erro ao finalizar venda: {str(e)}")

# ---------------- Funções Relatórios ----------------
def carregar_relatorios():
    try:
        for row in tree_vendas.get_children():
            tree_vendas.delete(row)

        cursor.execute("""
        SELECT id, DATE(data), total_geral
        FROM vendas
        ORDER BY data DESC
        """)
        vendas = cursor.fetchall()
        
        for venda in vendas:
            tree_vendas.insert("", tk.END, values=venda)

        if vendas:
            data_mais_recente = vendas[0][1]
            total_data_recente = 0
            for venda in vendas:
                if venda[1] == data_mais_recente:
                    total_data_recente += venda[2]
            
            label_total_dia.config(text=f"Total de {data_mais_recente}: R$ {total_data_recente:.2f}")
        else:
            label_total_dia.config(text="Total: R$ 0.00")
        
    except Exception as e:
        messagebox.showerror("Erro", f"Erro ao carregar relatórios: {str(e)}")

def ver_detalhes_venda():
    selection = tree_vendas.selection()
    if not selection:
        messagebox.showwarning("Atenção", "Selecione uma venda para ver detalhes!")
        return
        
    venda_id = tree_vendas.item(selection[0])['values'][0]
    
    detalhes_window = tk.Toplevel(root)
    detalhes_window.title(f"Detalhes da Venda #{venda_id}")
    detalhes_window.geometry("600x400")
    
    columns = ("Produto", "Qtd", "Preço Unit.", "Total")
    tree_detalhes = ttk.Treeview(detalhes_window, columns=columns, show="headings", height=15)
    
    for col in columns:
        tree_detalhes.heading(col, text=col)
        tree_detalhes.column(col, width=120)
    
    tree_detalhes.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
    
    cursor.execute("""
    SELECT p.nome, i.quantidade, i.preco_unitario, i.total_item
    FROM itens_venda i
    JOIN produtos p ON i.produto_id = p.id
    WHERE i.venda_id = ?
    """, (venda_id,))
    
    for item in cursor.fetchall():
        tree_detalhes.insert("", tk.END, values=item)
    
    btn_imprimir = ttk.Button(detalhes_window, text="Imprimir Cupom", 
                             command=lambda: imprimir_cupom(venda_id))
    btn_imprimir.pack(pady=5)

def imprimir_cupom(venda_id):
    cursor.execute("""
    SELECT v.id, v.data, v.total_geral, p.nome, i.quantidade, i.preco_unitario, i.total_item
    FROM vendas v
    JOIN itens_venda i ON v.id = i.venda_id
    JOIN produtos p ON i.produto_id = p.id
    WHERE v.id = ?
    """, (venda_id,))
    
    itens = cursor.fetchall()
    
    if not itens:
        messagebox.showerror("Erro", "Venda não encontrada!")
        return
    
    conteudo = "SUPERMERCADO PYTHON\n"
    conteudo += "CUPOM FISCAL\n"
    conteudo += f"Venda: #{venda_id} - {itens[0][1]}\n"
    conteudo += "-" * 40 + "\n"
    
    for item in itens:
        conteudo += f"{item[3][:20]:<20} {item[4]}x R${item[5]:.2f}\n"
        conteudo += f"{'':<20} R${item[6]:.2f}\n"
    
    conteudo += "-" * 40 + "\n"
    conteudo += f"TOTAL: R${itens[0][2]:.2f}\n"
    conteudo += "Obrigado pela preferência!\n"
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as f:
        f.write(conteudo)
        temp_file = f.name
    
    try:
        if os.name == 'nt':  # Windows
            subprocess.run(['notepad', '/p', temp_file], check=False)
        else:  # Linux/Mac
            subprocess.run(['lp', temp_file], check=False)
        messagebox.showinfo("Sucesso", "Cupom enviado para impressão!")
    except:
        messagebox.showinfo("Cupom Gerado", f"Cupom salvo em: {temp_file}")

def relatorio_vendas_periodo():
    periodo_window = tk.Toplevel(root)
    periodo_window.title("Relatório por Período")
    periodo_window.geometry("300x200")
    
    ttk.Label(periodo_window, text="Data Início (YYYY-MM-DD):").pack(pady=5)
    entry_inicio = ttk.Entry(periodo_window)
    entry_inicio.pack(pady=5)
    entry_inicio.insert(0, date.today().strftime("%Y-%m-%d"))
    
    ttk.Label(periodo_window, text="Data Fim (YYYY-MM-DD):").pack(pady=5)
    entry_fim = ttk.Entry(periodo_window)
    entry_fim.pack(pady=5)
    entry_fim.insert(0, date.today().strftime("%Y-%m-%d"))
    
    def gerar_relatorio():
        inicio = entry_inicio.get()
        fim = entry_fim.get()
        
        try:
            cursor.execute("""
            SELECT DATE(data), SUM(total_geral), COUNT(*)
            FROM vendas 
            WHERE DATE(data) BETWEEN ? AND ?
            GROUP BY DATE(data)
            ORDER BY DATE(data)
            """, (inicio, fim))
            
            resultado = cursor.fetchall()
            
            result_window = tk.Toplevel(periodo_window)
            result_window.title("Resultado do Relatório")
            result_window.geometry("500x300")
            
            tree = ttk.Treeview(result_window, columns=("Data", "Total", "Vendas"), show="headings", height=10)
            tree.heading("Data", text="Data")
            tree.heading("Total", text="Total R$")
            tree.heading("Vendas", text="Nº Vendas")
            
            for col in ("Data", "Total", "Vendas"):
                tree.column(col, width=120)
            
            for row in resultado:
                tree.insert("", tk.END, values=row)
            
            tree.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
            
            # Calcula o total do período
            total_periodo = sum(row[1] for row in resultado)
            label_total_periodo = ttk.Label(result_window, text=f"Total do Período: R$ {total_periodo:.2f}", 
                                           font=("Arial", 12, "bold"))
            label_total_periodo.pack(pady=5)
            
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao gerar relatório: {str(e)}")
    
    ttk.Button(periodo_window, text="Gerar Relatório", command=gerar_relatorio).pack(pady=10)

def verificar_estoque_baixo():
    cursor.execute("SELECT nome, estoque FROM produtos WHERE estoque <= 5 ORDER BY estoque ASC")
    produtos_baixo = cursor.fetchall()
    
    if produtos_baixo:
        mensagem = "Produtos com estoque baixo:\n\n"
        for produto in produtos_baixo:
            mensagem += f"• {produto[0]} - {produto[1]} unidades\n"
        
        messagebox.showwarning("Alerta de Estoque", mensagem)
    else:
        messagebox.showinfo("Estoque", "Todos os produtos têm estoque suficiente!")

def backup_dados():
    data_atual = datetime.now().strftime("%Y%m%d_%H%M%S")
    arquivo_backup = f"backup_pdv_{data_atual}.db"
    
    try:
        copy2("pdv.db", arquivo_backup)
        messagebox.showinfo("Backup", f"Backup criado com sucesso!\nArquivo: {arquivo_backup}")
    except Exception as e:
        messagebox.showerror("Erro", f"Erro no backup: {str(e)}")

def criar_tooltip(widget, texto):
    def on_enter(event):
        tooltip = tk.Toplevel(widget)
        tooltip.wm_overrideredirect(True)
        tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
        label = tk.Label(tooltip, text=texto, background="lightyellow", relief="solid", borderwidth=1)
        label.pack()
        widget.tooltip = tooltip
    
    def on_leave(event):
        if hasattr(widget, 'tooltip'):
            widget.tooltip.destroy()
    
    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)

# ---------------- Interface ----------------
root = tk.Tk()
root.title("Sistema PDV - Supermercado")
root.geometry("900x700")

# Configuração de estilo
style = ttk.Style()
style.theme_use('clam')
style.configure("TButton", padding=6, relief="flat", background="#4CAF50", foreground="white")
style.configure("TLabel", background="white", foreground="black")
style.configure("TFrame", background="white")
style.configure("Treeview", background="white", fieldbackground="white")
style.map("TButton", background=[('active', '#45a049')])

notebook = ttk.Notebook(root)
notebook.pack(expand=True, fill="both", padx=10, pady=10)

# --- Aba Produtos ---
frame_produtos = ttk.Frame(notebook, padding=10)
notebook.add(frame_produtos, text="📦 Produtos")

# Formulário de cadastro
form_frame = ttk.LabelFrame(frame_produtos, text="Cadastrar Novo Produto", padding=10)
form_frame.pack(fill=tk.X, pady=5)

ttk.Label(form_frame, text="Nome:*").grid(row=0, column=0, sticky=tk.W, pady=2)
entry_nome = ttk.Entry(form_frame, width=30)
entry_nome.grid(row=0, column=1, padx=5, pady=2)

ttk.Label(form_frame, text="Código Barras:").grid(row=0, column=2, sticky=tk.W, pady=2, padx=10)
entry_codigo_barras = ttk.Entry(form_frame, width=20)
entry_codigo_barras.grid(row=0, column=3, padx=5, pady=2)

ttk.Label(form_frame, text="Preço R$:*").grid(row=1, column=0, sticky=tk.W, pady=2)
entry_preco = ttk.Entry(form_frame, width=15)
entry_preco.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)

ttk.Label(form_frame, text="Estoque:*").grid(row=1, column=2, sticky=tk.W, pady=2, padx=10)
entry_estoque = ttk.Entry(form_frame, width=10)
entry_estoque.grid(row=1, column=3, sticky=tk.W, padx=5, pady=2)

btn_cadastrar = ttk.Button(form_frame, text="Cadastrar Produto", command=cadastrar_produto)
btn_cadastrar.grid(row=2, column=0, columnspan=4, pady=10)

# Lista de produtos
list_frame = ttk.LabelFrame(frame_produtos, text="Estoque de Produtos", padding=10)
list_frame.pack(expand=True, fill=tk.BOTH, pady=5)

columns = ("ID", "Nome", "Preço", "Estoque", "Código Barras")
tree_estoque = ttk.Treeview(list_frame, columns=columns, show="headings", height=12)

for col in columns:
    tree_estoque.heading(col, text=col)
    tree_estoque.column(col, width=100)

scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree_estoque.yview)
tree_estoque.configure(yscrollcommand=scrollbar.set)

tree_estoque.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

# --- Aba Vendas ---
frame_vendas = ttk.Frame(notebook, padding=10)
notebook.add(frame_vendas, text="💰 Vendas")

# Frame para adicionar produtos
add_frame = ttk.LabelFrame(frame_vendas, text="Adicionar Produto à Venda", padding=10)
add_frame.pack(fill=tk.X, pady=5)

ttk.Label(add_frame, text="Código de Barras:").grid(row=0, column=0, sticky=tk.W, pady=2)
entry_codigo = ttk.Entry(add_frame, width=15)
entry_codigo.grid(row=0, column=1, padx=5, pady=2)
entry_codigo.bind('<Return>', lambda e: buscar_por_codigo())

ttk.Label(add_frame, text="Ou digite o nome:").grid(row=1, column=0, sticky=tk.W, pady=2)
entry_produto = ttk.Entry(add_frame, width=30)
entry_produto.grid(row=1, column=1, padx=5, pady=2)
entry_produto.bind('<KeyRelease>', update_sugestoes)
entry_produto.bind('<FocusOut>', hide_sugestoes)

# Frame para sugestões de produtos
frame_sugestoes = tk.Frame(add_frame, bg='white', relief=tk.SUNKEN, borderwidth=1)
lista_sugestoes = tk.Listbox(frame_sugestoes, height=4, bg='white')
lista_sugestoes.pack(fill=tk.X)
lista_sugestoes.bind('<ButtonRelease-1>', on_produto_selected)

frame_sugestoes.grid(row=1, column=2, rowspan=2, sticky='nsew', padx=5)
frame_sugestoes.grid_remove()

ttk.Label(add_frame, text="Quantidade:*").grid(row=2, column=0, sticky=tk.W, pady=2)
entry_qtd = ttk.Entry(add_frame, width=10)
entry_qtd.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)

button_frame = ttk.Frame(add_frame)
button_frame.grid(row=3, column=0, columnspan=3, pady=10)

btn_adicionar = ttk.Button(button_frame, text="Adicionar", command=adicionar_item)
btn_adicionar.pack(side=tk.LEFT, padx=5)

btn_remover = ttk.Button(button_frame, text="Remover Selecionado", command=remover_item)
btn_remover.pack(side=tk.LEFT, padx=5)

btn_finalizar = ttk.Button(button_frame, text="Finalizar Venda", command=finalizar_venda)
btn_finalizar.pack(side=tk.LEFT, padx=5)

# Carrinho de compras
cart_frame = ttk.LabelFrame(frame_vendas, text="Carrinho de Compras", padding=10)
cart_frame.pack(expand=True, fill=tk.BOTH, pady=5)

lista = tk.Listbox(cart_frame, height=12, font=("Arial", 10))
lista.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

scrollbar_cart = ttk.Scrollbar(cart_frame, orient=tk.VERTICAL, command=lista.yview)
lista.configure(yscrollcommand=scrollbar_cart.set)
scrollbar_cart.pack(side=tk.RIGHT, fill=tk.Y)

label_total = ttk.Label(frame_vendas, text="Total: R$ 0.00", font=("Arial", 16, "bold"))
label_total.pack(pady=10)

# --- Aba Relatórios ---
frame_relatorios = ttk.Frame(notebook, padding=10)
notebook.add(frame_relatorios, text="📊 Relatórios")

# Treeview de vendas
report_frame = ttk.LabelFrame(frame_relatorios, text="Vendas Realizadas", padding=10)
report_frame.pack(expand=True, fill=tk.BOTH, pady=5)

columns_vendas = ("ID", "Data", "Total R$")
tree_vendas = ttk.Treeview(report_frame, columns=columns_vendas, show="headings", height=12)

for col in columns_vendas:
    tree_vendas.heading(col, text=col)
    tree_vendas.column(col, width=100)

scrollbar_vendas = ttk.Scrollbar(report_frame, orient=tk.VERTICAL, command=tree_vendas.yview)
tree_vendas.configure(yscrollcommand=scrollbar_vendas.set)

tree_vendas.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
scrollbar_vendas.pack(side=tk.RIGHT, fill=tk.Y)

# Botões e totais
bottom_frame = ttk.Frame(frame_relatorios)
bottom_frame.pack(fill=tk.X, pady=10)

label_total_dia = ttk.Label(bottom_frame, text="Total: R$ 0.00", font=("Arial", 12, "bold"))
label_total_dia.pack(side=tk.LEFT, padx=10)

btn_atualizar = ttk.Button(bottom_frame, text="Atualizar", command=carregar_relatorios)
btn_atualizar.pack(side=tk.RIGHT, padx=5)

btn_detalhes = ttk.Button(bottom_frame, text="Ver Detalhes", command=ver_detalhes_venda)
btn_detalhes.pack(side=tk.RIGHT, padx=5)

btn_relatorio = ttk.Button(bottom_frame, text="Relatório por Período", command=relatorio_vendas_periodo)
btn_relatorio.pack(side=tk.RIGHT, padx=5)

# --- Menu de Utilidades ---
menu_frame = ttk.Frame(root)
menu_frame.pack(fill=tk.X, padx=10, pady=5)

btn_estoque = ttk.Button(menu_frame, text="Verificar Estoque Baixo", command=verificar_estoque_baixo)
btn_estoque.pack(side=tk.LEFT, padx=5)

btn_backup = ttk.Button(menu_frame, text="Fazer Backup", command=backup_dados)
btn_backup.pack(side=tk.LEFT, padx=5)

# Adicionar tooltips
criar_tooltip(btn_adicionar, "Adicionar produto ao carrinho")
criar_tooltip(btn_remover, "Remover produto selecionado do carrinho")
criar_tooltip(btn_finalizar, "Finalizar venda atual")
criar_tooltip(btn_estoque, "Verificar produtos com estoque baixo")
criar_tooltip(btn_backup, "Criar backup do banco de dados")
criar_tooltip(btn_relatorio, "Gerar relatório de vendas por período")

# ---------------- Inicialização ----------------
lista_produtos = carregar_lista_produtos()
carregar_estoque()
carregar_relatorios()
verificar_estoque_baixo()

entry_produto.focus()

root.mainloop()
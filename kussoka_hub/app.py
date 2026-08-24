import json
import os
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g, jsonify, abort, Response
)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "kussoka.db")
SEED_PATH = os.path.join(BASE_DIR, "cursos_seed.json")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("KUSSOKA_SECRET_KEY", "kussoka-hub-chave-de-desenvolvimento")

# Conta de administrador criada automaticamente no primeiro arranque.
ADMIN_EMAIL = "admin@kussokahub.com"
ADMIN_SENHA_PADRAO = "admin123"

# Janela de tempo para considerar um utilizador "online" no painel admin.
JANELA_ONLINE_MINUTOS = 5

# Quantos cursos aparecem em amostra na página inicial.
TOTAL_CURSOS_AMOSTRA_HOME = 8

CATEGORIAS_LABELS = {
    "programacao": "Programação & Dev",
    "redes": "Redes & Segurança",
    "design": "Design & UI/UX",
    "negocios": "Negócios & Marketing",
    "idiomas": "Idiomas",
    "dados": "Dados & IA",
    "outros": "Outros",
}


# ---------------------------------------------------------------------------
# Banco de dados
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Cria as tabelas (se não existirem) e semeia os cursos/admin iniciais."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            senha_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            data_criacao TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cursos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            plataforma TEXT NOT NULL,
            categoria TEXT NOT NULL,
            duracao TEXT,
            nivel TEXT,
            imagem TEXT,
            url TEXT NOT NULL,
            descricao TEXT,
            embed_bloqueado INTEGER NOT NULL DEFAULT 0,
            data_criacao TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS matriculas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            curso_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'salvo',
            data_criacao TEXT NOT NULL,
            UNIQUE(usuario_id, curso_id),
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE,
            FOREIGN KEY (curso_id) REFERENCES cursos (id) ON DELETE CASCADE
        );
        """
    )
    db.commit()

    # Migração leve: garante a coluna "ultimo_login" mesmo em bases já existentes.
    colunas = [c["name"] for c in db.execute("PRAGMA table_info(usuarios)").fetchall()]
    if "ultimo_login" not in colunas:
        db.execute("ALTER TABLE usuarios ADD COLUMN ultimo_login TEXT")
        db.commit()

    # Semear administrador padrão
    cur = db.execute("SELECT id FROM usuarios WHERE email = ?", (ADMIN_EMAIL,))
    if cur.fetchone() is None:
        db.execute(
            "INSERT INTO usuarios (nome, email, senha_hash, is_admin, data_criacao) VALUES (?, ?, ?, 1, ?)",
            ("Administrador", ADMIN_EMAIL, generate_password_hash(ADMIN_SENHA_PADRAO), datetime.utcnow().isoformat()),
        )
        db.commit()

    # Semear cursos a partir do cursos_seed.json (apenas se a tabela estiver vazia)
    total_cursos = db.execute("SELECT COUNT(*) AS c FROM cursos").fetchone()["c"]
    if total_cursos == 0 and os.path.exists(SEED_PATH):
        with open(SEED_PATH, "r", encoding="utf-8") as f:
            cursos = json.load(f)
        for c in cursos:
            db.execute(
                """INSERT INTO cursos (titulo, plataforma, categoria, duracao, nivel, imagem, url, descricao, data_criacao)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    c.get("titulo", "Curso sem título"),
                    c.get("plataforma", "Plataforma desconhecida"),
                    c.get("categoria", "outros"),
                    c.get("duracao", ""),
                    c.get("nivel", ""),
                    c.get("imagem", ""),
                    c.get("url", "#"),
                    c.get("descricao", ""),
                    datetime.utcnow().isoformat(),
                ),
            )
        db.commit()

    db.close()


# ---------------------------------------------------------------------------
# Auxiliares de autenticação
# ---------------------------------------------------------------------------

@app.before_request
def carregar_usuario_logado():
    g.usuario = None
    uid = session.get("usuario_id")
    if uid:
        db = get_db()
        g.usuario = db.execute("SELECT * FROM usuarios WHERE id = ?", (uid,)).fetchone()
        if g.usuario is not None:
            # "Heartbeat" de atividade, com um intervalo mínimo para não sobrecarregar a BD.
            atualizar_agora = True
            if g.usuario["ultimo_login"]:
                try:
                    ultimo = datetime.fromisoformat(g.usuario["ultimo_login"])
                    atualizar_agora = (datetime.utcnow() - ultimo) > timedelta(minutes=1)
                except ValueError:
                    atualizar_agora = True
            if atualizar_agora:
                db.execute(
                    "UPDATE usuarios SET ultimo_login = ? WHERE id = ?",
                    (datetime.utcnow().isoformat(), uid),
                )
                db.commit()


@app.after_request
def aplicar_cabecalhos_seguranca(resposta):
    """Cabeçalhos básicos de segurança recomendados para qualquer plataforma web."""
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resposta.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return resposta


def login_obrigatorio(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.usuario is None:
            flash("Precisas de iniciar sessão para aceder a essa página.", "aviso")
            return redirect(url_for("login", proximo=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_obrigatorio(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.usuario is None:
            flash("Precisas de iniciar sessão para aceder a essa página.", "aviso")
            return redirect(url_for("login"))
        if not g.usuario["is_admin"]:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def injetar_globais():
    return {
        "usuario_atual": g.get("usuario"),
        "categorias_labels": CATEGORIAS_LABELS,
        "ano_atual": datetime.utcnow().year,
        "endpoint_atual": request.endpoint,
    }


# ---------------------------------------------------------------------------
# Rotas públicas
# ---------------------------------------------------------------------------

def _matriculas_ids_utilizador(db):
    """Ids dos cursos já guardados/em curso do utilizador autenticado."""
    if not g.usuario:
        return set()
    rows = db.execute(
        "SELECT curso_id FROM matriculas WHERE usuario_id = ?", (g.usuario["id"],)
    ).fetchall()
    return {r["curso_id"] for r in rows}


@app.route("/")
def index():
    db = get_db()
    total_cursos_catalogo = db.execute("SELECT COUNT(*) AS c FROM cursos").fetchone()["c"]
    total_plataformas = db.execute(
        "SELECT COUNT(DISTINCT plataforma) AS c FROM cursos"
    ).fetchone()["c"]

    # Amostra fixa de cursos para a página inicial (uma pequena vitrine, não o catálogo completo).
    cursos_amostra = db.execute(
        "SELECT * FROM cursos ORDER BY RANDOM() LIMIT ?",
        (TOTAL_CURSOS_AMOSTRA_HOME,),
    ).fetchall()

    return render_template(
        "index.html",
        cursos=cursos_amostra,
        matriculas_ids=_matriculas_ids_utilizador(db),
        total_cursos_catalogo=total_cursos_catalogo,
        total_plataformas=total_plataformas,
    )


@app.route("/cursos")
def cursos_catalogo():
    db = get_db()
    termo = request.args.get("q", "").strip()
    categoria = request.args.get("categoria", "").strip()

    query = "SELECT * FROM cursos WHERE 1=1"
    params = []
    if termo:
        query += " AND (titulo LIKE ? OR plataforma LIKE ? OR categoria LIKE ?)"
        like = f"%{termo}%"
        params += [like, like, like]
    if categoria:
        query += " AND categoria = ?"
        params.append(categoria)
    query += " ORDER BY data_criacao DESC"

    cursos = db.execute(query, params).fetchall()
    categorias_disponiveis = db.execute(
        "SELECT DISTINCT categoria FROM cursos ORDER BY categoria"
    ).fetchall()

    return render_template(
        "cursos.html",
        cursos=cursos,
        termo=termo,
        categoria_selecionada=categoria,
        categorias_disponiveis=[c["categoria"] for c in categorias_disponiveis],
        matriculas_ids=_matriculas_ids_utilizador(db),
        total_cursos=len(cursos),
    )


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if g.usuario:
        return redirect(url_for("index"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        confirmar_senha = request.form.get("confirmar_senha", "")

        erro = None
        if not nome or not email or not senha:
            erro = "Preenche todos os campos, por favor."
        elif len(senha) < 6:
            erro = "A senha deve ter pelo menos 6 caracteres."
        elif senha != confirmar_senha:
            erro = "As senhas não coincidem."

        db = get_db()
        if erro is None:
            existente = db.execute("SELECT id FROM usuarios WHERE email = ?", (email,)).fetchone()
            if existente:
                erro = "Já existe uma conta registada com esse email."

        if erro:
            flash(erro, "erro")
            return render_template("cadastro.html", nome=nome, email=email)

        db.execute(
            "INSERT INTO usuarios (nome, email, senha_hash, is_admin, data_criacao) VALUES (?, ?, ?, 0, ?)",
            (nome, email, generate_password_hash(senha), datetime.utcnow().isoformat()),
        )
        db.commit()
        flash("Conta criada com sucesso! Já podes iniciar sessão.", "sucesso")
        return redirect(url_for("login"))

    return render_template("cadastro.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.usuario:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        proximo = request.form.get("proximo") or url_for("index")

        db = get_db()
        usuario = db.execute("SELECT * FROM usuarios WHERE email = ?", (email,)).fetchone()

        if usuario is None or not check_password_hash(usuario["senha_hash"], senha):
            flash("Email ou senha incorretos.", "erro")
            return render_template("login.html", email=email, proximo=proximo)

        session.clear()
        session["usuario_id"] = usuario["id"]
        db.execute(
            "UPDATE usuarios SET ultimo_login = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), usuario["id"]),
        )
        db.commit()
        flash(f"Bem-vindo de volta, {usuario['nome']}!", "sucesso")
        return redirect(proximo)

    proximo = request.args.get("proximo") or url_for("index")
    return render_template("login.html", proximo=proximo)


@app.route("/logout")
def logout():
    session.clear()
    flash("Sessão terminada com sucesso.", "sucesso")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Curso / visualizador (iframe)
# ---------------------------------------------------------------------------

@app.route("/curso/<int:curso_id>")
@login_obrigatorio
def visualizar_curso(curso_id):
    db = get_db()
    curso = db.execute("SELECT * FROM cursos WHERE id = ?", (curso_id,)).fetchone()
    if curso is None:
        abort(404)

    matricula = db.execute(
        "SELECT * FROM matriculas WHERE usuario_id = ? AND curso_id = ?",
        (g.usuario["id"], curso_id),
    ).fetchone()

    return render_template("curso.html", curso=curso, matricula=matricula)


@app.route("/curso/<int:curso_id>/status", methods=["POST"])
@login_obrigatorio
def atualizar_status_curso(curso_id):
    db = get_db()
    curso = db.execute("SELECT id FROM cursos WHERE id = ?", (curso_id,)).fetchone()
    if curso is None:
        abort(404)

    status = request.form.get("status", "salvo")
    if status not in ("salvo", "em_andamento", "concluido"):
        status = "salvo"

    existente = db.execute(
        "SELECT id FROM matriculas WHERE usuario_id = ? AND curso_id = ?",
        (g.usuario["id"], curso_id),
    ).fetchone()

    if existente:
        db.execute("UPDATE matriculas SET status = ? WHERE id = ?", (status, existente["id"]))
    else:
        db.execute(
            "INSERT INTO matriculas (usuario_id, curso_id, status, data_criacao) VALUES (?, ?, ?, ?)",
            (g.usuario["id"], curso_id, status, datetime.utcnow().isoformat()),
        )
    db.commit()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "status": status})

    flash("Estado do curso atualizado.", "sucesso")
    return redirect(url_for("visualizar_curso", curso_id=curso_id))


@app.route("/curso/<int:curso_id>/remover", methods=["POST"])
@login_obrigatorio
def remover_curso_da_lista(curso_id):
    db = get_db()
    db.execute(
        "DELETE FROM matriculas WHERE usuario_id = ? AND curso_id = ?",
        (g.usuario["id"], curso_id),
    )
    db.commit()
    flash("Curso removido da tua lista.", "sucesso")
    return redirect(request.referrer or url_for("meus_cursos"))


@app.route("/meus-cursos")
@login_obrigatorio
def meus_cursos():
    db = get_db()
    linhas = db.execute(
        """SELECT c.*, m.status, m.data_criacao AS data_matricula
           FROM matriculas m
           JOIN cursos c ON c.id = m.curso_id
           WHERE m.usuario_id = ?
           ORDER BY m.data_criacao DESC""",
        (g.usuario["id"],),
    ).fetchall()
    return render_template("meus_cursos.html", cursos=linhas)


# ---------------------------------------------------------------------------
# Painel de Administração
# ---------------------------------------------------------------------------

@app.route("/admin")
@admin_obrigatorio
def admin_dashboard():
    db = get_db()
    total_usuarios = db.execute("SELECT COUNT(*) AS c FROM usuarios").fetchone()["c"]
    total_cursos = db.execute("SELECT COUNT(*) AS c FROM cursos").fetchone()["c"]
    total_matriculas = db.execute("SELECT COUNT(*) AS c FROM matriculas").fetchone()["c"]

    limite_online = (datetime.utcnow() - timedelta(minutes=JANELA_ONLINE_MINUTOS)).isoformat()
    total_online = db.execute(
        "SELECT COUNT(*) AS c FROM usuarios WHERE ultimo_login IS NOT NULL AND ultimo_login >= ?",
        (limite_online,),
    ).fetchone()["c"]

    total_em_andamento = db.execute(
        "SELECT COUNT(*) AS c FROM matriculas WHERE status = 'em_andamento'"
    ).fetchone()["c"]

    cursos_populares = db.execute(
        """SELECT c.id, c.titulo, c.plataforma, COUNT(m.id) AS total
           FROM cursos c LEFT JOIN matriculas m ON m.curso_id = c.id
           GROUP BY c.id ORDER BY total DESC LIMIT 5"""
    ).fetchall()

    usuarios_recentes = db.execute(
        "SELECT * FROM usuarios ORDER BY data_criacao DESC LIMIT 5"
    ).fetchall()

    usuarios_online = db.execute(
        "SELECT * FROM usuarios WHERE ultimo_login IS NOT NULL AND ultimo_login >= ? ORDER BY ultimo_login DESC",
        (limite_online,),
    ).fetchall()

    atividade_recente = db.execute(
        """SELECT u.nome AS usuario_nome, u.id AS usuario_id, c.titulo AS curso_titulo,
                  c.plataforma AS curso_plataforma, m.status, m.data_criacao
           FROM matriculas m
           JOIN usuarios u ON u.id = m.usuario_id
           JOIN cursos c ON c.id = m.curso_id
           WHERE m.status = 'em_andamento'
           ORDER BY m.data_criacao DESC LIMIT 8"""
    ).fetchall()

    return render_template(
        "admin_dashboard.html",
        total_usuarios=total_usuarios,
        total_cursos=total_cursos,
        total_matriculas=total_matriculas,
        total_online=total_online,
        total_em_andamento=total_em_andamento,
        cursos_populares=cursos_populares,
        usuarios_recentes=usuarios_recentes,
        usuarios_online=usuarios_online,
        atividade_recente=atividade_recente,
        janela_online_minutos=JANELA_ONLINE_MINUTOS,
    )


@app.route("/admin/usuarios")
@admin_obrigatorio
def admin_usuarios():
    db = get_db()
    limite_online = (datetime.utcnow() - timedelta(minutes=JANELA_ONLINE_MINUTOS)).isoformat()
    usuarios = db.execute(
        """SELECT u.*, COUNT(m.id) AS total_cursos,
                  (u.ultimo_login IS NOT NULL AND u.ultimo_login >= ?) AS online
           FROM usuarios u LEFT JOIN matriculas m ON m.usuario_id = u.id
           GROUP BY u.id ORDER BY u.data_criacao DESC""",
        (limite_online,),
    ).fetchall()
    return render_template("admin_usuarios.html", usuarios=usuarios)


@app.route("/admin/usuarios/<int:usuario_id>")
@admin_obrigatorio
def admin_usuario_detalhe(usuario_id):
    db = get_db()
    usuario = db.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    if usuario is None:
        abort(404)
    cursos = db.execute(
        """SELECT c.*, m.status, m.data_criacao AS data_matricula
           FROM matriculas m JOIN cursos c ON c.id = m.curso_id
           WHERE m.usuario_id = ? ORDER BY m.data_criacao DESC""",
        (usuario_id,),
    ).fetchall()
    return render_template("admin_usuario_detalhe.html", usuario=usuario, cursos=cursos)


@app.route("/admin/usuarios/<int:usuario_id>/admin", methods=["POST"])
@admin_obrigatorio
def admin_alternar_admin(usuario_id):
    if usuario_id == g.usuario["id"]:
        flash("Não podes remover o teu próprio acesso de administrador.", "erro")
        return redirect(url_for("admin_usuarios"))

    db = get_db()
    usuario = db.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    if usuario is None:
        abort(404)
    novo_valor = 0 if usuario["is_admin"] else 1
    db.execute("UPDATE usuarios SET is_admin = ? WHERE id = ?", (novo_valor, usuario_id))
    db.commit()
    flash("Permissões do utilizador atualizadas.", "sucesso")
    return redirect(url_for("admin_usuarios"))


@app.route("/admin/usuarios/<int:usuario_id>/excluir", methods=["POST"])
@admin_obrigatorio
def admin_excluir_usuario(usuario_id):
    if usuario_id == g.usuario["id"]:
        flash("Não podes excluir a tua própria conta a partir daqui.", "erro")
        return redirect(url_for("admin_usuarios"))
    db = get_db()
    db.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
    db.commit()
    flash("Utilizador excluído.", "sucesso")
    return redirect(url_for("admin_usuarios"))


@app.route("/admin/cursos")
@admin_obrigatorio
def admin_cursos():
    db = get_db()
    cursos = db.execute(
        """SELECT c.*, COUNT(m.id) AS total_alunos
           FROM cursos c LEFT JOIN matriculas m ON m.curso_id = c.id
           GROUP BY c.id ORDER BY c.data_criacao DESC"""
    ).fetchall()
    return render_template("admin_cursos.html", cursos=cursos)


@app.route("/admin/cursos/novo", methods=["GET", "POST"])
@admin_obrigatorio
def admin_curso_novo():
    if request.method == "POST":
        dados = _extrair_dados_curso_do_form()
        db = get_db()
        db.execute(
            """INSERT INTO cursos (titulo, plataforma, categoria, duracao, nivel, imagem, url, descricao, embed_bloqueado, data_criacao)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (*dados, datetime.utcnow().isoformat()),
        )
        db.commit()
        flash("Curso adicionado com sucesso.", "sucesso")
        return redirect(url_for("admin_cursos"))

    return render_template("admin_curso_form.html", curso=None)


@app.route("/admin/cursos/<int:curso_id>/editar", methods=["GET", "POST"])
@admin_obrigatorio
def admin_curso_editar(curso_id):
    db = get_db()
    curso = db.execute("SELECT * FROM cursos WHERE id = ?", (curso_id,)).fetchone()
    if curso is None:
        abort(404)

    if request.method == "POST":
        dados = _extrair_dados_curso_do_form()
        db.execute(
            """UPDATE cursos SET titulo=?, plataforma=?, categoria=?, duracao=?, nivel=?,
               imagem=?, url=?, descricao=?, embed_bloqueado=? WHERE id=?""",
            (*dados, curso_id),
        )
        db.commit()
        flash("Curso atualizado com sucesso.", "sucesso")
        return redirect(url_for("admin_cursos"))

    return render_template("admin_curso_form.html", curso=curso)


@app.route("/admin/cursos/<int:curso_id>/excluir", methods=["POST"])
@admin_obrigatorio
def admin_curso_excluir(curso_id):
    db = get_db()
    db.execute("DELETE FROM cursos WHERE id = ?", (curso_id,))
    db.commit()
    flash("Curso excluído.", "sucesso")
    return redirect(url_for("admin_cursos"))


def _extrair_dados_curso_do_form():
    f = request.form
    return (
        f.get("titulo", "").strip(),
        f.get("plataforma", "").strip(),
        f.get("categoria", "outros").strip(),
        f.get("duracao", "").strip(),
        f.get("nivel", "").strip(),
        f.get("imagem", "").strip(),
        f.get("url", "").strip(),
        f.get("descricao", "").strip(),
        1 if f.get("embed_bloqueado") == "on" else 0,
    )


# ---------------------------------------------------------------------------
# Erros
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def erro_404(e):
    return render_template("erro.html", codigo=404, mensagem="Página não encontrada."), 404


@app.errorhandler(403)
def erro_403(e):
    return render_template("erro.html", codigo=403, mensagem="Não tens permissão para aceder a essa página."), 403


@app.errorhandler(500)
def erro_500(e):
    return render_template("erro.html", codigo=500, mensagem="Ocorreu um erro interno. Tenta novamente em breve."), 500


# ---------------------------------------------------------------------------
# SEO — robots.txt e sitemap.xml
# ---------------------------------------------------------------------------

@app.route("/robots.txt")
def robots_txt():
    linhas = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin",
        "Disallow: /meus-cursos",
        f"Sitemap: {request.url_root.rstrip('/')}/sitemap.xml",
    ]
    return Response("\n".join(linhas), mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    db = get_db()
    paginas_estaticas = [
        url_for("index"),
        url_for("cursos_catalogo"),
        url_for("login"),
        url_for("cadastro"),
    ]
    urls_cursos = [url_for("visualizar_curso", curso_id=c["id"]) for c in db.execute("SELECT id FROM cursos").fetchall()]

    raiz = request.url_root.rstrip("/")
    itens = "".join(
        f"<url><loc>{raiz}{caminho}</loc></url>" for caminho in paginas_estaticas + urls_cursos
    )
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{itens}</urlset>'
    return Response(xml, mimetype="application/xml")


# ---------------------------------------------------------------------------

init_db()

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)

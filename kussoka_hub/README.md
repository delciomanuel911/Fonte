# Kussoka Hub

Plataforma agregadora de cursos online gratuitos. Reúne cursos de várias
plataformas (Cisco NetAcad, Microsoft Learn, IFRS, etc.) num único lugar,
onde o utilizador se regista, faz login, pesquisa e acede aos cursos através
de um visualizador embutido (iframe) sem sair do Kussoka Hub. Inclui também
um painel de administração.

## Funcionalidades

- **Design responsivo** com paleta natural (verde + terracota + areia),
  tipografia Poppins/Inter e logotipo estruturado.
- **Cadastro / Login** de utilizadores (senha protegida com hash).
- **Página inicial** com amostra de 6 cursos em destaque e uma secção
  "Sobre" completa (Visão, Missão, Valores).
- **Catálogo completo** (`/cursos`) com pesquisa por palavra-chave e
  filtro por categoria — separado da página inicial.
- **Visualizador embutido (iframe)** — o utilizador acede ao curso de outra
  plataforma sem sair do Kussoka Hub, com botão de "abrir em aba externa"
  como plano B caso o site bloqueie o iframe.
- **"Meus Cursos"** — cada utilizador pode guardar cursos e marcar o estado
  (guardado / a fazer / concluído).
- **Painel de Administração** (`/admin`) — layout em sidebar, só acessível
  a administradores:
  - Painel de informações: total de cursos, total de utilizadores,
    utilizadores online agora e cursos em andamento.
  - Lista de utilizadores online e atividade recente (quem está a fazer
    o quê).
  - Lista de todos os utilizadores, com os cursos que cada um está a fazer.
  - Gestão completa de cursos (adicionar, editar, excluir).
  - Promover/remover permissões de administrador de outros utilizadores.
- **SEO**: meta tags, Open Graph, `robots.txt` e `sitemap.xml` gerados
  automaticamente.

## Como correr o projeto

```bash
cd kussoka_hub
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

A aplicação fica disponível em **http://localhost:5000**.

Na primeira execução, o ficheiro `kussoka.db` (SQLite) é criado
automaticamente, e os cursos de `cursos_seed.json` são importados.

## Conta de administrador padrão

```
Email: admin@kussokahub.com
Senha: admin123
```

**Importante:** troca essa senha (ou cria outra conta admin e apaga esta)
antes de colocares o site em produção.

## Estrutura do projeto

```
kussoka_hub/
├── app.py                  # Aplicação Flask (rotas, autenticação, admin)
├── cursos_seed.json         # Cursos iniciais importados na 1ª execução
├── kussoka.db                # Base de dados SQLite (gerada automaticamente)
├── requirements.txt
├── templates/                # Páginas HTML (Jinja2)
└── static/
    ├── css/                   # style.css (site) + curso.css (visualizador)
    └── js/                    # main.js (menu mobile, etc.)
```

## Adicionar mais cursos / plataformas

Podes adicionar cursos de duas formas:

1. **Pelo painel Admin** → `Admin` → `Cursos` → `+ Novo Curso`.
2. Editando `cursos_seed.json` **antes** da primeira execução (ele só é
   importado quando a tabela de cursos está vazia).

Qualquer plataforma com curso gratuito pode ser adicionada — basta o link
público do curso. Se a plataforma bloquear exibição em iframe (ex. algumas
usam cabeçalhos `X-Frame-Options`), marca a opção "bloqueia iframe" no
formulário para mostrar um aviso ao utilizador com o botão de abrir em nova
aba.

## Possíveis próximos passos

- Recuperação de senha por email.
- Avaliações/comentários dos utilizadores sobre cada curso.
- Todas as abas do administrador devem ser totalmente (100%) responsiva na versão mobile, que nenhuma linha e palavra se quebre ou fique fora do lugar
- Segurança contra ataques hackers ou cibernético
- Apenas o admin principal pode remover ou nomear outros usuários como admin (os que forem adicionados como admin não podem remover o admin principal como admin)!
- 

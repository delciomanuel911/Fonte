// Kussoka Hub — interações de interface
document.addEventListener('DOMContentLoaded', () => {
  // Menu mobile (hambúrguer)
  let btn = document.getElementById('btn');
  let menu = document.getElementById('menu');

  btn.addEventListener('click', ()=>{
    menu.classList.add('ativo');
  });
  menu.addEventListener('click', ()=>{
    menu.classList.remove('ativo');
  });

  // Fecha as mensagens flash automaticamente após alguns segundos
  const flashes = document.querySelectorAll('.flash');
  flashes.forEach((el) => {
    setTimeout(() => {
      el.style.transition = 'opacity 0.5s ease';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 500);
    }, 5000);
  });

  // Botão "voltar ao topo"
  const btnTopo = document.getElementById('btn-topo');
  if (btnTopo) {
    window.addEventListener('scroll', () => {
      btnTopo.classList.toggle('visivel', window.scrollY > 400);
    });
    btnTopo.addEventListener('click', () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }
});

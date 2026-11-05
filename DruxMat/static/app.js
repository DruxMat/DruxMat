'use strict';
(() => {
  const year = document.getElementById('year');
  if (year) year.textContent = new Date().getFullYear();
  const header = document.getElementById('header');
  const nav = document.getElementById('navlinks');
  const menu = document.getElementById('hamb');
  const dropdown = document.getElementById('navDropdown');
  function closeMenu(){if(nav&&menu){nav.classList.remove('open');menu.setAttribute('aria-expanded','false');menu.setAttribute('aria-label','Otwórz menu')}if(dropdown)dropdown.open=false}
  if (menu && nav) {
    menu.addEventListener('click',()=>{
      const isOpen=nav.classList.toggle('open');
      menu.setAttribute('aria-expanded',String(isOpen));
      menu.setAttribute('aria-label',isOpen?'Zamknij menu':'Otwórz menu');
    });
    nav.querySelectorAll('a').forEach(link => link.addEventListener('click',closeMenu));
    document.addEventListener('keydown',event=>{if(event.key==='Escape')closeMenu()});
    document.addEventListener('click',event=>{if(!event.target.closest('.header'))closeMenu()});
  }
  if (header) {
    let busy = false;
    const progress=()=>{
      const doc=document.documentElement;
      const max=doc.scrollHeight-doc.clientHeight;
      header.style.setProperty('--scroll-progress',max>0?`${Math.min(100,Math.max(0,doc.scrollTop/max*100))}%`:'0%');
      busy=false;
    };
    window.addEventListener('scroll',()=>{if(!busy){busy=true;requestAnimationFrame(progress)}},{passive:true});
    window.addEventListener('resize',progress);
    progress();
  }
  const filters=Array.from(document.querySelectorAll('[data-filter]'));
  const cards=Array.from(document.querySelectorAll('[data-service-category]'));
  function setFilter(category){
    if(!filters.length)return;
    const valid=filters.some(button=>button.dataset.filter===category)?category:'all';
    filters.forEach(button=>{const active=button.dataset.filter===valid;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active))});
    cards.forEach(card=>card.hidden=!(valid==='all'||card.dataset.serviceCategory===valid));
  }
  filters.forEach(button=>button.addEventListener('click',()=>setFilter(button.dataset.filter)));
  document.querySelectorAll('[data-category]').forEach(link=>link.addEventListener('click',()=>setFilter(link.dataset.category)));
  try {
    if (window.location.hash === '#uslugi' && sessionStorage.getItem('druxmatCategory')) {
      setFilter(sessionStorage.getItem('druxmatCategory'));
      sessionStorage.removeItem('druxmatCategory');
    }
    document.querySelectorAll('[data-category]').forEach(link=>link.addEventListener('click',()=>sessionStorage.setItem('druxmatCategory',link.dataset.category)));
  } catch (_error) { /* Storage may be unavailable when viewing a local HTML preview. */ }
  if('IntersectionObserver' in window && !matchMedia('(prefers-reduced-motion: reduce)').matches){
    const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('visible');observer.unobserve(entry.target)}}),{threshold:.06,rootMargin:'0px 0px -25px 0px'});
    document.querySelectorAll('.reveal').forEach(element=>observer.observe(element));
  }else document.querySelectorAll('.reveal').forEach(element=>element.classList.add('visible'));
  document.querySelectorAll('.pass-toggle').forEach(button=>button.addEventListener('click',()=>{
    const input=button.parentElement.querySelector('input');
    const showing=input.type==='password';input.type=showing?'text':'password';
    button.textContent=showing?'Ukryj':'Pokaż';button.setAttribute('aria-pressed',String(showing));
  }));
  const fileInput=document.getElementById('order-files');
  const fileList=document.getElementById('preview-name');
  if(fileInput&&fileList)fileInput.addEventListener('change',()=>{
    const files=Array.from(fileInput.files);
    const size=files.reduce((sum,file)=>sum+file.size,0);
    if(files.length>4||size>24*1024*1024||files.some(file=>file.size>12*1024*1024)){
      fileInput.setCustomValidity('Maksymalnie 4 pliki, do 12 MB na plik i 24 MB łącznie.');
      fileList.textContent='Przekroczono limit liczby lub rozmiaru plików.';
    }else{
      fileInput.setCustomValidity('');
      fileList.textContent=files.length?`Wybrano ${files.length} plik(ów): ${files.map(f=>f.name).join(', ')}`:'';
    }
  });
})();

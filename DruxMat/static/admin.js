'use strict';
(() => {
  const date = document.getElementById('adminDate');
  if (date) date.textContent = new Intl.DateTimeFormat('pl-PL', {dateStyle:'long'}).format(new Date());
  const forms = document.querySelectorAll('.order-edit');
  forms.forEach(form=>form.addEventListener('submit',()=>{
    const button=form.querySelector('button[type=submit]');
    if(button){button.disabled=true;button.textContent='Zapisywanie…';}
  }));
})();

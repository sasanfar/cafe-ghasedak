(() => {
  const input = document.getElementById('story-search');
  const status = document.getElementById('search-status');
  if (!input || !status) return;
  const entries = [...document.querySelectorAll('.archive-entry')];
  const groups = [...document.querySelectorAll('.archive-group')];
  const normalize = value => value.toLocaleLowerCase('fa').replace(/[يى]/g, 'ی').replace(/ك/g, 'ک').replace(/[۰-۹]/g, digit => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(digit))).trim();
  input.addEventListener('input', () => {
    const query = normalize(input.value);
    let matches = 0;
    for (const entry of entries) {
      const visible = normalize(entry.dataset.search || '').includes(query);
      entry.hidden = !visible;
      if (visible) matches++;
    }
    for (const group of groups) group.hidden = !group.querySelector('.archive-entry:not([hidden])');
    status.textContent = query ? `${matches} نوشته پیدا شد.` : '';
  });
})();

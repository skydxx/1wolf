(function () {
  var script = document.currentScript || document.querySelector('script[data-max-files]');
  var MAX = parseInt(script.getAttribute('data-max-files'), 10) || 5;
  var MAX_MB = parseInt(script.getAttribute('data-max-mb'), 10) || 8;

  var drop = document.getElementById('drop');
  var input = document.getElementById('files');
  var list = document.getElementById('filelist');
  if (!drop || !input || !list) return;

  var chosen = [];

  function human(bytes) {
    return bytes < 1048576 ? Math.round(bytes / 1024) + ' КБ' : (bytes / 1048576).toFixed(1) + ' МБ';
  }

  function render() {
    var dt = new DataTransfer();
    chosen.forEach(function (f) { dt.items.add(f); });
    input.files = dt.files;
    list.textContent = '';
    chosen.forEach(function (f, i) {
      var row = document.createElement('div');
      row.className = 'f';
      var name = document.createElement('span');
      name.className = 'nm';
      name.textContent = f.name;
      var size = document.createElement('span');
      size.className = 'sz';
      size.textContent = human(f.size);
      var remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'rm';
      remove.textContent = '✕';
      remove.setAttribute('aria-label', 'Убрать файл');
      remove.addEventListener('click', function () { chosen.splice(i, 1); render(); });
      row.appendChild(name); row.appendChild(size); row.appendChild(remove);
      list.appendChild(row);
    });
  }

  function add(files) {
    Array.prototype.forEach.call(files, function (f) {
      if (chosen.length >= MAX) return;
      if (f.size > MAX_MB * 1048576) return;
      var dup = chosen.some(function (x) { return x.name === f.name && x.size === f.size; });
      if (!dup) chosen.push(f);
    });
    render();
  }

  drop.addEventListener('click', function () { input.click(); });
  drop.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); }
  });
  input.addEventListener('change', function (e) { add(e.target.files); });
  ['dragenter', 'dragover'].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('over'); });
  });
  ['dragleave', 'drop'].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove('over'); });
  });
  drop.addEventListener('drop', function (e) { add(e.dataTransfer.files); });

  var form = drop.closest('form');
  if (form) {
    form.addEventListener('submit', function () {
      var btn = form.querySelector('button[type=submit]');
      if (btn) { btn.disabled = true; btn.textContent = 'Отправляем…'; }
    });
  }
})();

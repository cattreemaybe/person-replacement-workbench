const $ = (selector) => document.querySelector(selector);
const personInput = $('#personInput');
const sceneInput = $('#sceneInput');
const personPreview = $('#personPreview');
const canvas = $('#canvas');
const ctx = canvas.getContext('2d');
const stage = $('#stage');
const resultImage = $('#resultImage');
const emptyState = $('#emptyState');
const generateBtn = $('#generateBtn');
const statusEl = $('#status');
const selectionReadout = $('#selectionReadout');
const resetBox = $('#resetBox');
const compareBtn = $('#compareBtn');
const downloadBtn = $('#downloadBtn');
const modeSelect = $('#modeSelect');
const keyWrap = $('#keyWrap');
const busy = $('#busy');
const segmentBtn = $('#segmentBtn');
const maskState = $('#maskState');

const state = {
  personData: '', sceneData: '', sceneImage: null,
  box: null, drawing: false, start: null, resultData: '',
  maskData: '', maskImage: null, segmenting: false,
};

function fileToDataURL(file) {
  return new Promise((resolve, reject) => {
    if (!file || !/^image\/(jpeg|png|webp)$/.test(file.type)) return reject(new Error('请选择 JPG、PNG 或 WEBP 图片。'));
    if (file.size > 20 * 1024 * 1024) return reject(new Error('单张图片请不要超过 20MB。'));
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('无法读取图片，请重新选择。'));
    reader.readAsDataURL(file);
  });
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error('图片预览失败，请换一张图片。'));
    image.src = src;
  });
}

function setStatus(text, error = false) {
  statusEl.textContent = text;
  statusEl.classList.toggle('error', error);
}

function updateSteps() {
  $('#personStep').classList.toggle('ready', !!state.personData);
  $('#sceneStep').classList.toggle('active', !!state.personData && !state.sceneData);
  $('#sceneStep').classList.toggle('ready', !!state.sceneData);
  $('#generateStep').classList.toggle('active', !!state.personData && !!state.sceneData);
  generateBtn.disabled = !(state.personData && state.sceneData && state.box && state.maskData) || !busy.hidden;
  segmentBtn.disabled = !state.box || state.segmenting || !busy.hidden;
  if (state.resultData) return;
  if (!state.personData) setStatus('请先上传人物 A。');
  else if (!state.sceneData) setStatus('接下来上传复杂场景照。');
  else if (!state.box) setStatus('请在场景中拖动，框住要替换的人物 B。');
  else if (!state.maskData) setStatus(state.segmenting ? '正在本机识别人物轮廓…' : '请识别并确认人物轮廓。');
  else setStatus(modeSelect.value === 'demo' ? '演示模式不会调用模型，可用于检查框选和导出。' : '准备好了。点击“开始替换”。');
}

function fitCanvas() {
  if (!state.sceneImage) return;
  const availableW = Math.max(280, stage.clientWidth - 40);
  const availableH = Math.max(340, stage.clientHeight - 40);
  const scale = Math.min(availableW / state.sceneImage.naturalWidth, availableH / state.sceneImage.naturalHeight, 1);
  canvas.style.width = `${Math.round(state.sceneImage.naturalWidth * scale)}px`;
  canvas.style.height = `${Math.round(state.sceneImage.naturalHeight * scale)}px`;
  resultImage.style.width = canvas.style.width;
  resultImage.style.height = canvas.style.height;
}

function draw() {
  if (!state.sceneImage) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(state.sceneImage, 0, 0, canvas.width, canvas.height);
  if (state.maskImage) {
    const overlay = document.createElement('canvas');
    overlay.width = canvas.width; overlay.height = canvas.height;
    const ox = overlay.getContext('2d');
    ox.drawImage(state.maskImage, 0, 0, canvas.width, canvas.height);
    // A grayscale PNG is opaque in both its black and white areas. Use its
    // brightness as alpha; otherwise the black background also turns red.
    const pixels = ox.getImageData(0, 0, canvas.width, canvas.height);
    for (let i = 0; i < pixels.data.length; i += 4) {
      const maskValue = pixels.data[i];
      pixels.data[i] = 227;
      pixels.data[i + 1] = 74;
      pixels.data[i + 2] = 50;
      pixels.data[i + 3] = Math.round(maskValue * 0.48);
    }
    ox.putImageData(pixels, 0, 0);
    ctx.drawImage(overlay, 0, 0);
  }
  if (state.box) {
    const { x, y, width, height } = state.box;
    ctx.save();
    ctx.fillStyle = 'rgba(190, 53, 38, .13)';
    ctx.strokeStyle = '#e34a32';
    ctx.lineWidth = Math.max(3, canvas.width / 500);
    ctx.setLineDash([Math.max(8, canvas.width / 100), Math.max(5, canvas.width / 160)]);
    ctx.fillRect(x, y, width, height);
    ctx.strokeRect(x, y, width, height);
    ctx.restore();
    selectionReadout.textContent = `选框：${Math.round(width)} × ${Math.round(height)} px，起点 (${Math.round(x)}, ${Math.round(y)})`;
  } else selectionReadout.textContent = '选框：尚未选择';
}

function canvasPoint(event) {
  const rect = canvas.getBoundingClientRect();
  const pointer = event.touches ? event.touches[0] : event;
  return {
    x: Math.max(0, Math.min(canvas.width, (pointer.clientX - rect.left) * canvas.width / rect.width)),
    y: Math.max(0, Math.min(canvas.height, (pointer.clientY - rect.top) * canvas.height / rect.height)),
  };
}

function beginDraw(event) {
  if (!state.sceneImage || !resultImage.hidden) return;
  event.preventDefault();
  state.drawing = true;
  state.start = canvasPoint(event);
  state.box = { x: state.start.x, y: state.start.y, width: 0, height: 0 };
  canvas.setPointerCapture?.(event.pointerId);
}

function moveDraw(event) {
  if (!state.drawing) return;
  event.preventDefault();
  const p = canvasPoint(event);
  state.box = {
    x: Math.min(state.start.x, p.x), y: Math.min(state.start.y, p.y),
    width: Math.abs(p.x - state.start.x), height: Math.abs(p.y - state.start.y),
  };
  draw();
}

function endDraw(event) {
  if (!state.drawing) return;
  event.preventDefault();
  state.drawing = false;
  if (state.box.width * state.box.height < 900) state.box = null;
  state.maskData = ''; state.maskImage = null;
  resetBox.disabled = !state.box;
  draw();
  updateSteps();
  if (state.box) identifyMask();
}

async function identifyMask() {
  if (!state.box || state.segmenting) return;
  state.segmenting = true; state.maskData = ''; state.maskImage = null;
  maskState.textContent = '识别中…'; maskState.classList.remove('ready');
  updateSteps(); draw();
  try {
    const response = await fetch('/api/segment', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({scene: state.sceneData, box: state.box, expand: Number($('#expand').value)}),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || '人物轮廓识别失败。');
    state.maskData = payload.mask;
    state.maskImage = await loadImage(payload.mask);
    maskState.textContent = `已识别 · ${Math.min(100, Math.max(0, Math.round(payload.score * 100)))}%`;
    maskState.classList.add('ready');
    setStatus('请检查红色轮廓。确认无误后即可开始替换。');
    draw();
  } catch (error) {
    maskState.textContent = '识别失败';
    setStatus(error.message, true);
  } finally {
    state.segmenting = false; updateSteps();
  }
}

personInput.addEventListener('change', async () => {
  try {
    state.personData = await fileToDataURL(personInput.files[0]);
    personPreview.src = state.personData;
    personPreview.closest('.upload').classList.add('has-image');
    personPreview.nextElementSibling.querySelector('strong').textContent = personInput.files[0].name;
    updateSteps();
  } catch (error) { setStatus(error.message, true); }
});

sceneInput.addEventListener('change', async () => {
  try {
    state.sceneData = await fileToDataURL(sceneInput.files[0]);
    state.sceneImage = await loadImage(state.sceneData);
    state.box = null; state.maskData = ''; state.maskImage = null;
    state.resultData = '';
    canvas.width = state.sceneImage.naturalWidth;
    canvas.height = state.sceneImage.naturalHeight;
    emptyState.hidden = true;
    canvas.classList.add('visible');
    resultImage.classList.remove('visible');
    resultImage.hidden = true;
    $('#sceneLabel').textContent = sceneInput.files[0].name;
    $('#stageTitle').textContent = '拖动鼠标，框住人物 B';
    resetBox.disabled = true;
    compareBtn.disabled = true;
    downloadBtn.hidden = true;
    fitCanvas(); draw(); updateSteps();
  } catch (error) { setStatus(error.message, true); }
});

canvas.addEventListener('pointerdown', beginDraw);
canvas.addEventListener('pointermove', moveDraw);
canvas.addEventListener('pointerup', endDraw);
canvas.addEventListener('pointercancel', endDraw);
window.addEventListener('resize', fitCanvas);

resetBox.addEventListener('click', () => {
  state.box = null;
  state.maskData = ''; state.maskImage = null;
  maskState.textContent = '等待框选'; maskState.classList.remove('ready');
  state.resultData = '';
  resultImage.classList.remove('visible'); resultImage.hidden = true;
  canvas.classList.add('visible');
  compareBtn.disabled = true; downloadBtn.hidden = true; resetBox.disabled = true;
  $('#stageTitle').textContent = '拖动鼠标，重新框选人物 B';
  draw(); updateSteps();
});

modeSelect.addEventListener('change', () => {
  keyWrap.hidden = modeSelect.value === 'demo';
  updateSteps();
});
$('#feather').addEventListener('input', (e) => $('#featherValue').textContent = `${e.target.value} px`);
$('#expand').addEventListener('input', (e) => $('#expandValue').textContent = `${Number(e.target.value) >= 0 ? '+' : ''}${e.target.value} px`);
$('#expand').addEventListener('change', identifyMask);
segmentBtn.addEventListener('click', identifyMask);

function showOriginal(show) {
  if (!state.resultData) return;
  canvas.classList.toggle('visible', show);
  resultImage.classList.toggle('visible', !show);
}
compareBtn.addEventListener('pointerdown', () => showOriginal(true));
compareBtn.addEventListener('pointerup', () => showOriginal(false));
compareBtn.addEventListener('pointerleave', () => showOriginal(false));
compareBtn.addEventListener('keydown', (e) => { if (e.code === 'Space' || e.code === 'Enter') showOriginal(true); });
compareBtn.addEventListener('keyup', () => showOriginal(false));

generateBtn.addEventListener('click', async () => {
  if (!state.box) return;
  busy.hidden = false; generateBtn.disabled = true; setStatus('正在处理，请保持页面打开。');
  try {
    const response = await fetch('/api/replace', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        person: state.personData, scene: state.sceneData, box: state.box, mask: state.maskData,
        mode: modeSelect.value, note: $('#note').value,
        feather: Number($('#feather').value),
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || '替换失败，请重试。');
    state.resultData = payload.image;
    resultImage.src = payload.image;
    await resultImage.decode();
    canvas.classList.remove('visible'); resultImage.hidden = false; resultImage.classList.add('visible');
    downloadBtn.href = payload.download; downloadBtn.download = payload.filename; downloadBtn.hidden = false;
    compareBtn.disabled = false;
    $('#stageTitle').textContent = payload.mode === 'demo' ? '演示结果 · 红框表示允许修改区域' : '替换完成 · 框外已锁定';
    setStatus(payload.mode === 'demo' ? '演示完成。切换到 GPT Image 2 可生成真实人物替换。' : '替换完成。可按住“看原图”比较，或下载 PNG。');
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    busy.hidden = true; updateSteps();
  }
});

fetch('/api/health').then(r => r.json()).then(({ apiKeyConfigured, provider, model }) => {
  $('#providerState').textContent = apiKeyConfigured ? `${provider} · 令牌已配置` : `${provider} · 等待填写令牌`;
  $('#providerModel').textContent = model;
}).catch(() => {});
updateSteps();

(() => {
  const banner = document.querySelector('[data-queue-alert]');
  const total = banner.querySelector('[data-alert-count]');
  const status = banner.querySelector('[data-alert-status]');
  const transport = banner.querySelector('[data-alert-transport]');
  const button = banner.querySelector('button');
  let revision = Number(banner.dataset.revision);
  let audio;
  let enabled = false;

  function announce() {
    if (audio?.state === 'running') {
      const tone = audio.createOscillator();
      const gain = audio.createGain();
      tone.frequency.value = 660;
      gain.gain.value = 0.12;
      tone.connect(gain).connect(audio.destination);
      tone.start();
      tone.stop(audio.currentTime + 0.22);
    }
    if ('Notification' in window && Notification.permission === 'granted') {
      try {
        new Notification('JT 工作台：P0 待复核', {body: '请查看工作台中的紧急信号。', tag: 'jt-workbench-p0'});
      } catch {
        status.textContent = '浏览器通知不可用，仍显示页内告警。';
      }
    }
  }

  button.addEventListener('click', async () => {
    button.disabled = true;
    const enableSound = async () => {
      if (!('AudioContext' in window)) return false;
      audio = new AudioContext();
      await audio.resume();
      return audio.state === 'running';
    };
    const enableNotification = async () => {
      if (!('Notification' in window)) return false;
      const permission = Notification.permission === 'default'
        ? await Notification.requestPermission() : Notification.permission;
      return permission === 'granted';
    };
    const [sound, notification] = await Promise.allSettled([enableSound(), enableNotification()]);
    const hasSound = sound.status === 'fulfilled' && sound.value;
    const hasNotification = notification.status === 'fulfilled' && notification.value;
    enabled = hasSound || hasNotification;
    if (enabled) {
      button.textContent = '提醒已开启';
      status.textContent = hasSound && hasNotification ? '' : hasSound ? '浏览器通知未开启。' : '本地声音不可用。';
      if (Number(total.textContent)) announce();
    } else {
      button.disabled = false;
      status.textContent = '声音和浏览器通知均未开启，仍显示页内告警。';
    }
  });

  async function readAlerts() {
    try {
      const response = await fetch('/queue/alerts', {cache: 'no-store'});
      if (response.status === 401 || response.status === 403) {
        transport.textContent = '告警更新已停止，请重新登录。';
        return;
      }
      if (!response.ok) throw new Error('alert update unavailable');
      const next = await response.json();
      if (Number(total.textContent) !== next.pending) total.textContent = next.pending;
      banner.classList.toggle('urgent', next.pending > 0);
      transport.textContent = '';
      if (enabled && next.pending > 0 && next.revision !== revision) announce();
      revision = next.revision;
    } catch {
      transport.textContent = '告警暂未更新。';
    }
    window.setTimeout(readAlerts, 2000);
  }

  window.setTimeout(readAlerts, 2000);
})();

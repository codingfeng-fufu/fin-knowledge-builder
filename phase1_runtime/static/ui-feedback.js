(function () {
  function pulse(target) {
    if (!target || target.classList.contains('disabled') || target.disabled) {
      return;
    }
    target.classList.remove('ui-clicked');
    // Force reflow so repeated clicks retrigger the animation.
    void target.offsetWidth;
    target.classList.add('ui-clicked');
    window.setTimeout(() => {
      target.classList.remove('ui-clicked');
    }, 220);
  }

  document.addEventListener('pointerdown', (event) => {
    const target = event.target.closest(
      'button, a.nav-link, .sample-card, .compact-question-btn, .start-path-card, .home-path-card, .demo-flow-card, .demo-script-card'
    );
    if (target) {
      pulse(target);
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return;
    }
    const active = document.activeElement;
    if (active && active.matches('button, a.nav-link, .sample-card, .compact-question-btn, .start-path-card, .home-path-card, .demo-flow-card, .demo-script-card')) {
      pulse(active);
    }
  });
})();

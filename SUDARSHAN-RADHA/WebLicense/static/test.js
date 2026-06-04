(function () {
  'use strict';

  var TOTAL_SECS = 30 * 60;
  var remaining  = TOTAL_SECS;
  var display    = document.getElementById('timer-display');
  var form       = document.getElementById('test-form');
  var submitBtn  = document.getElementById('submit-btn');
  var expired    = false;

  function fmt(s) {
    var m   = Math.floor(s / 60);
    var sec = s % 60;
    return String(m).padStart(2, '0') + ':' + String(sec).padStart(2, '0');
  }

  display.textContent = fmt(remaining);

  var tick = setInterval(function () {
    remaining--;
    display.textContent = fmt(remaining);
    if (remaining <= 300) {
      display.classList.add('warn');
    }
    if (remaining <= 0) {
      clearInterval(tick);
      display.textContent = '00:00';
      expired = true;
      // Submit even with unanswered questions on time expiry
      form.removeAttribute('novalidate');
      var inputs = form.querySelectorAll('input[type="radio"][required]');
      inputs.forEach(function (el) { el.removeAttribute('required'); });
      form.submit();
    }
  }, 1000);

  // Warn before navigating away mid-test
  window.addEventListener('beforeunload', function (e) {
    if (!expired) {
      e.preventDefault();
      e.returnValue = '';
    }
  });

  // Remove beforeunload guard on intentional submit
  form.addEventListener('submit', function () {
    expired = true;
  });

  // Highlight selected option visually
  document.querySelectorAll('.options input[type="radio"]').forEach(function (radio) {
    radio.addEventListener('change', function () {
      var group = document.querySelectorAll(
        '.options input[name="' + this.name + '"]'
      );
      group.forEach(function (r) {
        r.closest('label').style.borderColor = '';
        r.closest('label').style.background  = '';
      });
      this.closest('label').style.borderColor = 'var(--cyan)';
      this.closest('label').style.background  = 'rgba(0,184,212,0.08)';
    });
  });

  // Live answered-question counter
  var totalQ   = document.querySelectorAll('.q-block').length;
  var answered = 0;

  function updateCounter() {
    var names = {};
    document.querySelectorAll('.options input[type="radio"]:checked').forEach(function (r) {
      names[r.name] = true;
    });
    answered = Object.keys(names).length;
    submitBtn.textContent = 'Submit Examination (' + answered + '/' + totalQ + ' answered)';
    submitBtn.disabled = false;
  }

  document.querySelectorAll('.options input[type="radio"]').forEach(function (r) {
    r.addEventListener('change', updateCounter);
  });

  updateCounter();
})();

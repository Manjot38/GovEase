/* GovEase Assistant UI. All Groq requests go through the Flask backend. */
(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    var root = document.createElement('div');
    root.className = 'govease-chat';
    root.innerHTML =
      '<button class="govease-chat-launch" type="button" ' +
        'aria-expanded="false" aria-controls="govease-chat-window" ' +
        'aria-label="Open GovEase Assistant">' +
        '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" ' +
          'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" ' +
          'stroke-linejoin="round">' +
          '<path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H5l-2 2v-9.5a7.5 7.5 0 1 1 17 0Z"/>' +
          '<path d="M8 10h8M8 14h5"/>' +
        '</svg>' +
        '<span>Ask GovEase</span>' +
      '</button>' +
      '<section class="govease-chat-window" id="govease-chat-window" ' +
        'role="dialog" aria-modal="false" aria-labelledby="govease-chat-title" hidden>' +
        '<header class="govease-chat-header">' +
          '<div><strong id="govease-chat-title">GovEase Assistant</strong>' +
          '<span>Government information, made simpler</span></div>' +
          '<button class="govease-chat-close" type="button" ' +
            'aria-label="Close GovEase Assistant">&times;</button>' +
        '</header>' +
        '<div class="govease-chat-messages" role="log" aria-live="polite" ' +
          'aria-relevant="additions text">' +
          '<p class="govease-chat-message govease-chat-assistant">' +
            'Hello! Ask me about Indian government services and schemes. ' +
            'Please confirm important details with an official source.' +
          '</p>' +
        '</div>' +
        '<form class="govease-chat-form">' +
          '<label class="visually-hidden" for="govease-chat-input">Your question</label>' +
          '<input id="govease-chat-input" type="text" maxlength="4000" ' +
            'placeholder="Type your question..." autocomplete="off" required>' +
          '<button type="submit">Send</button>' +
        '</form>' +
        '<p class="govease-chat-note">AI answers may be inaccurate. Check official sources.</p>' +
      '</section>';
    document.body.appendChild(root);

    var launch = root.querySelector('.govease-chat-launch');
    var close = root.querySelector('.govease-chat-close');
    var panel = root.querySelector('.govease-chat-window');
    var form = root.querySelector('.govease-chat-form');
    var input = root.querySelector('#govease-chat-input');
    var sendButton = form.querySelector('button[type="submit"]');
    var messages = root.querySelector('.govease-chat-messages');
    var closeTimer = null;

    function setOpen(open) {
      window.clearTimeout(closeTimer);
      launch.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) {
        panel.hidden = false;
        window.requestAnimationFrame(function () {
          panel.classList.add('is-open');
        });
        input.focus();
      } else {
        panel.classList.remove('is-open');
        closeTimer = window.setTimeout(function () {
          panel.hidden = true;
          launch.focus();
        }, 180);
      }
    }

    function appendMessage(text, kind) {
      var message = document.createElement('p');
      message.className = 'govease-chat-message govease-chat-' + kind;
      message.textContent = text;
      messages.appendChild(message);
      messages.scrollTop = messages.scrollHeight;
      return message;
    }

    launch.addEventListener('click', function () {
      setOpen(panel.hidden);
    });
    close.addEventListener('click', function () {
      setOpen(false);
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && !panel.hidden) setOpen(false);
    });

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      var message = input.value.trim();
      if (!message || sendButton.disabled) return;

      appendMessage(message, 'user');
      input.value = '';
      input.disabled = true;
      sendButton.disabled = true;

      var typing = document.createElement('p');
      typing.className = 'govease-chat-message govease-chat-assistant govease-chat-typing';
      typing.setAttribute('aria-label', 'GovEase Assistant is typing');
      typing.innerHTML = '<span></span><span></span><span></span>';
      messages.appendChild(typing);
      messages.scrollTop = messages.scrollHeight;

      var apiBase = window.GovEase && window.GovEase.config
        ? window.GovEase.config.API_BASE
        : (window.location.port === '5000' || window.location.protocol === 'file:'
          ? '/api'
          : 'http://localhost:5000/api');

      fetch(apiBase + '/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: message })
      })
        .then(function (response) {
          return response.json().catch(function () {
            return {};
          }).then(function (data) {
            if (!response.ok) {
              throw new Error(data.message || 'The chatbot could not answer right now.');
            }
            if (typeof data.response !== 'string' || !data.response.trim()) {
              throw new Error('The chatbot returned an empty answer. Please try again.');
            }
            return data.response;
          });
        })
        .then(function (answer) {
          typing.remove();
          appendMessage(answer, 'assistant');
        })
        .catch(function (error) {
          typing.remove();
          var errorMessage = error.message;
          if (error instanceof TypeError) {
            errorMessage = 'Could not connect to GovEase. Check that the backend is running and try again.';
          }
          appendMessage(errorMessage || 'Could not reach the chatbot. Please try again.', 'assistant');
        })
        .then(function () {
          input.disabled = false;
          sendButton.disabled = false;
          input.focus();
        });
    });
  });
})();

const sessionKey = 'aurora_nexus_session_id';
const guestKey = 'aurora_nexus_guest_id';

let sessionId = localStorage.getItem(sessionKey);
if (!sessionId) {
  sessionId = crypto.randomUUID();
  localStorage.setItem(sessionKey, sessionId);
}

let guestId = localStorage.getItem(guestKey);
if (!guestId) {
  guestId = `GST-web-${crypto.randomUUID().slice(0, 8)}`;
  localStorage.setItem(guestKey, guestId);
}

const API = window.APP_CONFIG;

const supportForm = document.getElementById('supportForm');
const issueTypeEl = document.getElementById('issueType');
const bookingIdEl = document.getElementById('bookingId');
const guestIdEl = document.getElementById('guestId');
const issueDescriptionEl = document.getElementById('issueDescription');
const submitBtn = document.getElementById('submitSupportBtn');
const supportResultEl = document.getElementById('supportResult');

guestIdEl.value = guestId;

function showResult(message, ok = true) {
  supportResultEl.textContent = message;
  supportResultEl.classList.remove('d-none', 'error', 'success');
  supportResultEl.classList.add(ok ? 'success' : 'error');
}

supportForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  submitBtn.disabled = true;

  const issueType = issueTypeEl.value;
  const description = issueDescriptionEl.value.trim();
  const bookingId = bookingIdEl.value.trim();
  const guest = guestIdEl.value.trim();

  if (!description || !guest) {
    showResult('Please provide guest ID and issue description.', false);
    submitBtn.disabled = false;
    return;
  }

  try {
    const response = await fetch(API.complaintEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        user_id: 'support-web-user',
        booking_id: bookingId || null,
        guest_id: guest,
        issue: `${issueType}: ${description}`,
        resolution: '',
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      const detail = data?.detail?.error?.message || 'Support request failed.';
      throw new Error(detail);
    }

    showResult(`Submitted successfully. ${data.status_detail || ''}`.trim(), true);
    issueDescriptionEl.value = '';
  } catch (error) {
    showResult(error.message || 'Support request failed.', false);
  } finally {
    submitBtn.disabled = false;
  }
});

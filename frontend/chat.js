// Page-lifetime only: refreshing the website creates a fresh session identity.
const sessionId = crypto.randomUUID();
const guestId = `GST-web-${crypto.randomUUID().slice(0, 8)}`;

const API = {
  chatEndpoint: '/chat',
  roomsEndpoint: '/rooms',
  bookingPreviewEndpoint: '/booking/preview',
  bookingPreviewCancelEndpoint: '/booking/preview/cancel',
  bookingEndpoint: '/booking',
  paymentPreviewEndpoint: '/payment/preview',
  paymentCancelEndpoint: '/payment/cancel',
  paymentEndpoint: '/payment',
};

const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const bookingLoaderEl = document.getElementById('bookingLoader');
const roomResultsEl = document.getElementById('roomResults');
const roomCardsEl = document.getElementById('roomCards');
const bookingProgressEl = document.getElementById('bookingProgress');
const conciergeLoaderEl = document.getElementById('conciergeLoader');
const conciergeLoaderTextEl = document.getElementById('conciergeLoaderText');
const actionCardsEl = document.getElementById('actionCards');
const sessionNoticeEl = document.getElementById('sessionNotice');

const bookingState = {
  guestName: null,
  stayPurpose: null,
  roomType: null,
  guestCount: null,
  checkinDate: null,
  checkoutDate: null,
  selectedRoomId: null,
  totalNights: null,
  paymentAmount: null,
  bookingId: null,
  bookingSource: 'web-chat',
  roomsLoaded: false,
};

const prematureConfirmationPatterns = [
  /booking confirmed/i,
  /your booking is confirmed/i,
  /reservation confirmed/i,
  /booking has been confirmed/i,
];

function formatCurrency(amount) {
  return new Intl.NumberFormat('en-MY', { style: 'currency', currency: 'MYR' }).format(amount);
}

function escapeHtml(text) {
  return (text || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function appendMessage(role, text) {
  const msg = document.createElement('article');
  msg.className = `chat-msg ${role === 'user' ? 'chat-user' : 'chat-ai'}`;
  msg.innerHTML = `<div class="chat-bubble">${escapeHtml(text)}</div>`;
  messagesEl.appendChild(msg);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function containsPrematureConfirmation(text) {
  return prematureConfirmationPatterns.some((pattern) => pattern.test(text || ''));
}

function normalizeAssistantMessage(chatData) {
  const responseText = chatData?.response || 'No response received.';
  const stage = chatData?.metadata?.stage;
  const paymentConfirmed = Boolean(chatData?.metadata?.payment_confirmed);

  if (containsPrematureConfirmation(responseText) && !(stage === 'confirmation' && paymentConfirmed)) {
    return 'Please continue with room recommendation, room selection, booking preview, and payment before confirmation is shown.';
  }

  return responseText;
}

function isInternalStageGuardMessage(text) {
  const lowered = (text || '').toLowerCase();
  return (
    lowered.includes('please continue with room recommendation')
    || lowered.includes('your booking is not finalized yet')
    || lowered.includes('required stage flow')
  );
}

function isNoAvailabilityMessage(text) {
  const lowered = (text || '').toLowerCase();
  return (
    lowered.includes('no availability')
    || lowered.includes("don't have any availability")
    || lowered.includes('fully booked')
  );
}

function setBusy(isBusy) {
  inputEl.disabled = isBusy;
  sendBtn.disabled = isBusy;
}

function showConciergeLoader(message) {
  if (!conciergeLoaderEl || !conciergeLoaderTextEl) return;
  conciergeLoaderTextEl.textContent = message;
  conciergeLoaderEl.classList.remove('d-none');
}

function hideConciergeLoader() {
  if (!conciergeLoaderEl) return;
  conciergeLoaderEl.classList.add('d-none');
}

function showRoomLoader(show) {
  bookingLoaderEl.classList.toggle('d-none', !show);
}

function showRoomResults(show) {
  roomResultsEl.classList.toggle('d-none', !show);
}

function showActionCards(show) {
  if (!actionCardsEl) return;
  actionCardsEl.classList.toggle('d-none', !show);
}

function clearActionCards() {
  if (!actionCardsEl) return;
  actionCardsEl.innerHTML = '';
  showActionCards(false);
}

function resetProgress() {
  if (!bookingProgressEl) return;
  bookingProgressEl.classList.remove('d-none');
  bookingProgressEl.querySelectorAll('.progress-step').forEach((stepEl) => {
    const statusEl = stepEl.querySelector('.step-status');
    if (!statusEl) return;
    statusEl.textContent = 'Pending';
    statusEl.className = 'step-status status-pending';
  });
}

function setStepStatus(stepName, status, text) {
  if (!bookingProgressEl) return;
  const stepEl = bookingProgressEl.querySelector(`.progress-step[data-step="${stepName}"]`);
  if (!stepEl) return;
  const statusEl = stepEl.querySelector('.step-status');
  if (!statusEl) return;

  statusEl.textContent = text;
  statusEl.className = `step-status status-${status}`;
}

function toIsoDate(rawDateText) {
  const clean = (rawDateText || '').trim();
  if (!clean) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(clean)) return clean;

  const currentYear = new Date().getFullYear();
  const candidate = /\d{4}$/.test(clean) ? clean : `${clean} ${currentYear}`;
  const parsed = new Date(candidate);
  if (Number.isNaN(parsed.getTime())) return null;

  const month = String(parsed.getMonth() + 1).padStart(2, '0');
  const day = String(parsed.getDate()).padStart(2, '0');
  return `${parsed.getFullYear()}-${month}-${day}`;
}

function parseSameMonthDayRange(message) {
  const match = message.match(/(\d{1,2})\s*[-–]\s*(\d{1,2})\s+([A-Za-z]+)\s*(\d{4})?/i);
  if (!match) return null;

  const startDay = Number(match[1]);
  const endDay = Number(match[2]);
  const monthText = match[3];
  const yearText = match[4] || String(new Date().getFullYear());

  if (Number.isNaN(startDay) || Number.isNaN(endDay) || endDay <= startDay) return null;

  const checkinIso = toIsoDate(`${startDay} ${monthText} ${yearText}`);
  const checkoutIso = toIsoDate(`${endDay} ${monthText} ${yearText}`);
  if (!checkinIso || !checkoutIso) return null;

  return { checkinIso, checkoutIso };
}

function renderBookingPreviewCard(preview) {
  if (!actionCardsEl) return;

  actionCardsEl.innerHTML = `
    <article class="action-card" data-card="booking-preview">
      <h3>Booking Preview</h3>
      <p><strong>Guest:</strong> ${escapeHtml(preview.guest_name || 'N/A')}</p>
      <p><strong>Room:</strong> ${escapeHtml(preview.room_type)} (${escapeHtml(preview.room_id)})</p>
      <p><strong>Guests:</strong> ${escapeHtml(String(preview.guest_count))}</p>
      <p><strong>Stay:</strong> ${escapeHtml(preview.checkin_date)} to ${escapeHtml(preview.checkout_date)}</p>
      <p><strong>Total Nights:</strong> ${escapeHtml(String(preview.total_nights))}</p>
      <p><strong>Total Price:</strong> ${escapeHtml(formatCurrency(preview.total_price || 0))}</p>
      <div class="action-buttons">
        <button type="button" class="action-btn primary" data-action="confirm-booking">Confirm Booking</button>
        <button type="button" class="action-btn secondary" data-action="cancel-booking-preview">Cancel</button>
      </div>
    </article>
  `;

  showActionCards(true);
}

function renderPaymentPreviewCard(preview) {
  if (!actionCardsEl) return;

  actionCardsEl.innerHTML = `
    <article class="action-card" data-card="payment-preview">
      <h3>Payment Preview</h3>
      <p><strong>Booking ID:</strong> ${escapeHtml(preview.booking_id)}</p>
      <p><strong>Amount:</strong> ${escapeHtml(formatCurrency(preview.amount))}</p>
      <div class="action-buttons">
        <button type="button" class="action-btn primary" data-action="pay-now">Pay Now</button>
        <button type="button" class="action-btn secondary" data-action="cancel-payment-preview">Cancel</button>
      </div>
    </article>
  `;

  showActionCards(true);
}

function parseBookingData(message) {
  const previous = {
    roomType: bookingState.roomType,
    guestCount: bookingState.guestCount,
    checkinDate: bookingState.checkinDate,
    checkoutDate: bookingState.checkoutDate,
  };

  const text = message.toLowerCase();

  const nameMatch = message.match(/(?:my name is|i am|i'm)\s+([a-zA-Z][a-zA-Z\s'-]{1,40})/i);
  if (nameMatch) bookingState.guestName = nameMatch[1].trim();

  if (text.includes('business')) bookingState.stayPurpose = 'business';
  if (text.includes('leisure') || text.includes('vacation') || text.includes('holiday')) bookingState.stayPurpose = 'leisure';

  if (text.includes('deluxe')) bookingState.roomType = 'Deluxe';
  if (text.includes('standard')) bookingState.roomType = 'Standard';
  if (text.includes('suite')) bookingState.roomType = 'Suite';

  const countMatch = text.match(/(\d+)\s*(guest|guests|pax|people|person)/);
  if (countMatch) bookingState.guestCount = Number(countMatch[1]);

  // Solo traveller phrases → 1 guest
  if (!bookingState.guestCount) {
    if (/\b(alone|solo|by myself|just me|travelling alone|traveling alone)\b/.test(text)) {
      bookingState.guestCount = 1;
    }
  }

  // Standalone single digit fallback (e.g. "15 may to 20 may, 1 , deluxe")
  if (!bookingState.guestCount) {
    const standaloneDigit = text.match(/(?:^|[,\s])([1-9])(?=[,\s]|$)/);
    if (standaloneDigit) bookingState.guestCount = Number(standaloneDigit[1]);
  }

  const checkinMatch = text.match(/checkin\s*(\d{4}-\d{2}-\d{2})/);
  if (checkinMatch) bookingState.checkinDate = checkinMatch[1];

  const checkoutMatch = text.match(/checkout\s*(\d{4}-\d{2}-\d{2})/);
  if (checkoutMatch) bookingState.checkoutDate = checkoutMatch[1];

  const naturalRangeMatch = message.match(
    /(\d{1,2}\s+[A-Za-z]+(?:\s+\d{4})?)\s*(?:to|until|till|til|-|–)\s*(\d{1,2}\s+[A-Za-z]+(?:\s+\d{4})?)/i,
  );
  if (naturalRangeMatch) {
    const checkinIso = toIsoDate(naturalRangeMatch[1]);
    const checkoutIso = toIsoDate(naturalRangeMatch[2]);
    if (checkinIso && checkoutIso) {
      bookingState.checkinDate = checkinIso;
      bookingState.checkoutDate = checkoutIso;
    }
  }

  if (!bookingState.checkinDate || !bookingState.checkoutDate) {
    const compactRange = parseSameMonthDayRange(message);
    if (compactRange) {
      bookingState.checkinDate = compactRange.checkinIso;
      bookingState.checkoutDate = compactRange.checkoutIso;
    }
  }

  if (text.includes('direct')) bookingState.bookingSource = 'direct';

  const changed = (
    previous.roomType !== bookingState.roomType
    || previous.guestCount !== bookingState.guestCount
    || previous.checkinDate !== bookingState.checkinDate
    || previous.checkoutDate !== bookingState.checkoutDate
  );
  if (changed) {
    bookingState.roomsLoaded = false;
    clearActionCards();
    showRoomResults(false);
  }
}

function canSearchRooms() {
  return (
    !!bookingState.guestName
    && !!bookingState.guestCount
    && !!bookingState.checkinDate
    && !!bookingState.checkoutDate
  );
}

async function postChat(message) {
  const response = await fetch(API.chatEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      user_id: guestId,
      message,
    }),
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data?.detail?.error?.message || data?.error?.message || 'Assistant temporarily unavailable.';
    throw new Error(detail);
  }
  return data;
}

function renderRooms(rooms) {
  roomCardsEl.innerHTML = '';
  if (!rooms || rooms.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-rooms';
    empty.textContent = 'No available rooms found for your criteria.';
    roomCardsEl.appendChild(empty);
    showRoomResults(true);
    return;
  }

  rooms.forEach((room) => {
    const card = document.createElement('article');
    card.className = 'room-card';
    card.innerHTML = `
      <h3>Room ${escapeHtml(String(room.room_id || 'N/A'))}</h3>
      <p><strong>Type:</strong> ${escapeHtml(room.room_type || 'N/A')}</p>
      <p><strong>Floor:</strong> ${escapeHtml(String(room.floor || 'N/A'))}</p>
      <p><strong>Zone:</strong> ${escapeHtml(room.zone || 'N/A')}</p>
      <p><strong>Capacity:</strong> ${escapeHtml(String(room.capacity || 'N/A'))} Guests</p>
      <p><strong>Rate:</strong> ${escapeHtml(formatCurrency(room.price_per_night || 0))} / night</p>
      <p><strong>Noise Level:</strong> ${escapeHtml(room.noise_level || 'N/A')}</p>
      <button
        type="button"
        data-room-id="${escapeHtml(String(room.room_id || ''))}"
        data-room-type="${escapeHtml(String(room.room_type || ''))}"
        class="select-room-btn"
      >Select Room</button>
    `;
    roomCardsEl.appendChild(card);
  });

  showRoomResults(true);
}

function renderNoRoomsAlternatives(alternatives) {
  roomCardsEl.innerHTML = '';
  const empty = document.createElement('div');
  empty.className = 'empty-rooms';

  if (alternatives && alternatives.length) {
    const options = alternatives.map((range, index) => `${index + 1}. ${range}`).join('\n');
    empty.textContent = `Those dates are currently fully booked. Nearby available windows:\n${options}\nWould any of these work for your stay?`;
  } else {
    empty.textContent = 'Those dates are currently fully booked. Please try nearby dates and I will check again.';
  }

  roomCardsEl.appendChild(empty);
  showRoomResults(true);
}

async function loadRoomsAndRender() {
  showConciergeLoader('Preparing your curated room recommendations...');
  showRoomLoader(true);
  showRoomResults(false);
  roomCardsEl.innerHTML = '';

  try {
    const query = new URLSearchParams({
      session_id: sessionId,
      user_id: guestId,
      checkin_date: bookingState.checkinDate,
      checkout_date: bookingState.checkoutDate,
      guest_count: String(bookingState.guestCount),
    });

    if (bookingState.roomType) {
      query.set('room_type', bookingState.roomType);
    }

    const response = await fetch(`${API.roomsEndpoint}?${query.toString()}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.detail?.error?.message || 'Unable to search rooms right now.');
    }

    bookingState.roomsLoaded = true;
    if (!data.rooms || data.rooms.length === 0) {
      renderNoRoomsAlternatives(data.alternatives || []);
    } else {
      renderRooms(data.rooms || []);
    }
  } catch (error) {
    appendMessage('assistant', `Room search failed: ${error.message}`);
  } finally {
    showRoomLoader(false);
    hideConciergeLoader();
  }
}

async function openBookingPreview(selectedRoomId) {
  const stayPurpose = bookingState.stayPurpose || 'leisure';
  const response = await fetch(API.bookingPreviewEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      guest_id: guestId,
      guest_name: bookingState.guestName,
      stay_purpose: stayPurpose,
      checkin_date: bookingState.checkinDate,
      checkout_date: bookingState.checkoutDate,
      room_type: bookingState.roomType,
      room_id: selectedRoomId,
      guest_count: bookingState.guestCount,
    }),
  });

  const previewData = await response.json();
  if (!response.ok) {
    const validationError = Array.isArray(previewData?.detail)
      ? previewData.detail.map((item) => item?.msg).filter(Boolean).join('; ')
      : null;
    const stringDetail = typeof previewData?.detail === 'string' ? previewData.detail : null;
    const detail = previewData?.detail?.error?.message || validationError || stringDetail || 'Booking preview failed.';
    throw new Error(detail);
  }
  return previewData;
}

async function confirmBooking(selectedRoomId) {
  const response = await fetch(API.bookingEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      guest_id: guestId,
      checkin_date: bookingState.checkinDate,
      checkout_date: bookingState.checkoutDate,
      room_type: bookingState.roomType,
      room_id: selectedRoomId,
      guest_count: bookingState.guestCount,
      booking_source: bookingState.bookingSource,
    }),
  });

  const bookingData = await response.json();
  if (!response.ok) {
    const detail = bookingData?.detail?.error?.message || 'Booking request failed.';
    throw new Error(detail);
  }

  return bookingData;
}

async function openPaymentPreview(bookingId) {
  const response = await fetch(API.paymentPreviewEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      booking_id: bookingId,
    }),
  });

  const paymentPreviewData = await response.json();
  if (!response.ok) {
    const detail = paymentPreviewData?.detail?.error?.message || 'Payment preview failed.';
    throw new Error(detail);
  }

  return paymentPreviewData;
}

async function confirmPayment(bookingId, amount) {
  const response = await fetch(API.paymentEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      user_id: guestId,
      booking_id: bookingId,
      guest_id: guestId,
      amount,
      payment_status: 'success',
      transaction_id: `TXN-WEB-${crypto.randomUUID().slice(0, 8).toUpperCase()}`,
    }),
  });

  const paymentData = await response.json();
  if (!response.ok) {
    const detail = paymentData?.detail?.error?.message || 'Payment request failed.';
    throw new Error(detail);
  }

  return paymentData;
}

async function openBookingFlow(selectedRoomId) {
  try {
    setBusy(true);
    resetProgress();
    clearActionCards();

    showConciergeLoader('Preparing your booking preview...');
    setStepStatus('preview', 'active', 'In Progress');
    const preview = await openBookingPreview(selectedRoomId);
    setStepStatus('preview', 'done', 'Done');
    hideConciergeLoader();

    bookingState.selectedRoomId = selectedRoomId;
    bookingState.totalNights = preview.total_nights;

    renderBookingPreviewCard(preview);
    appendMessage('assistant', 'Booking preview is ready. Please confirm or cancel below.');
  } catch (error) {
    hideConciergeLoader();
    const allSteps = ['preview', 'booking', 'payment_preview', 'payment', 'confirmation'];
    const firstPending = allSteps.find((step) => {
      const el = bookingProgressEl?.querySelector(`.progress-step[data-step="${step}"] .step-status`);
      return el?.classList.contains('status-pending') || el?.classList.contains('status-active');
    });
    if (firstPending) {
      setStepStatus(firstPending, 'error', 'Failed');
    }
    appendMessage('assistant', `Booking failed: ${error.message}`);
  } finally {
    setBusy(false);
  }
}

async function handleConfirmBooking() {
  if (!bookingState.selectedRoomId) {
    appendMessage('assistant', 'Please select a room first.');
    return;
  }

  try {
    setBusy(true);
    showConciergeLoader('Securing your reservation details...');

    setStepStatus('booking', 'active', 'In Progress');
    const bookingData = await confirmBooking(bookingState.selectedRoomId);
    bookingState.bookingId = bookingData.booking_id;
    setStepStatus('booking', 'done', 'Done');

    setStepStatus('payment_preview', 'active', 'In Progress');
    showConciergeLoader('Preparing your payment summary...');
    const paymentPreview = await openPaymentPreview(bookingData.booking_id);
    setStepStatus('payment_preview', 'done', 'Done');
    bookingState.paymentAmount = paymentPreview.amount;

    hideConciergeLoader();
    renderPaymentPreviewCard(paymentPreview);
    appendMessage('assistant', 'Payment preview is ready. Please proceed with payment or cancel.');
  } catch (error) {
    hideConciergeLoader();
    const failedStep = bookingState.bookingId ? 'payment_preview' : 'booking';
    setStepStatus(failedStep, 'error', 'Failed');
    appendMessage('assistant', `Booking failed: ${error.message}`);
  } finally {
    setBusy(false);
  }
}

async function handlePayNow() {
  if (!bookingState.bookingId || !bookingState.paymentAmount) {
    appendMessage('assistant', 'Payment preview is missing. Please confirm booking first.');
    return;
  }

  let paymentCompleted = false;

  try {
    setBusy(true);
    showConciergeLoader('Processing your payment securely...');

    setStepStatus('payment', 'active', 'In Progress');
    const paymentResult = await confirmPayment(bookingState.bookingId, bookingState.paymentAmount);
    if (paymentResult?.stage !== 'confirmation') {
      throw new Error('Booking process not completed. Please finish payment before confirmation.');
    }
    paymentCompleted = true;
    setStepStatus('payment', 'done', 'Paid');
    clearActionCards();

    showConciergeLoader('Finalizing your confirmation...');
    const confirmationPrompt = [
      `Please provide final booking confirmation details for booking id ${bookingState.bookingId}.`,
      'Payment has been completed successfully. Use the confirmation format with booking and room details.',
      `Guest count: ${bookingState.guestCount}`,
    ].join(' ');

    const chatData = await postChat(confirmationPrompt);
    if (chatData?.metadata?.stage !== 'confirmation' || !chatData?.metadata?.payment_confirmed) {
      throw new Error('Final confirmation is not available yet. Please complete the workflow in order.');
    }
    setStepStatus('confirmation', 'done', 'Done');
    clearActionCards();
    hideConciergeLoader();
    appendMessage('assistant', normalizeAssistantMessage(chatData));
  } catch (error) {
    hideConciergeLoader();
    const message = error?.message || '';
    const quotaExceeded = /resource_exhausted|quota|\b429\b/i.test(message);

    if (paymentCompleted && quotaExceeded) {
      setStepStatus('confirmation', 'active', 'Awaiting LLM');
      appendMessage(
        'assistant',
        'Payment is successful and your booking is already confirmed in the workflow. Final confirmation text is delayed because the Gemini quota limit was hit. Please wait about a minute, then send "confirm booking" and I will render your final confirmation summary.',
      );
    } else if (message.includes('Final confirmation is not available yet')) {
      setStepStatus('confirmation', 'error', 'Blocked');
      appendMessage('assistant', `Confirmation blocked: ${message}`);
    } else if (paymentCompleted && message.includes('Cannot process payment before booking confirmation stage.')) {
      setStepStatus('payment', 'done', 'Paid');
      setStepStatus('confirmation', 'active', 'Awaiting LLM');
      appendMessage('assistant', 'Payment was already completed. Please send "confirm booking" to fetch the final confirmation message.');
    } else {
      setStepStatus('payment', 'error', 'Failed');
      appendMessage('assistant', `Payment failed: ${message}`);
    }
  } finally {
    setBusy(false);
  }
}

async function handleCancelBookingPreview() {
  try {
    await fetch(API.bookingPreviewCancelEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        guest_id: guestId,
      }),
    });
  } catch {
    // Do not block UX if cancel transition API is unavailable.
  }

  clearActionCards();
  setStepStatus('preview', 'error', 'Cancelled');
  setStepStatus('booking', 'pending', 'Pending');
  setStepStatus('payment_preview', 'pending', 'Pending');
  setStepStatus('payment', 'pending', 'Pending');
  setStepStatus('confirmation', 'pending', 'Pending');
  appendMessage('assistant', 'Booking preview cancelled. Returning to room recommendations.');
}

async function handleCancelPaymentPreview() {
  try {
    await fetch(API.paymentCancelEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
      }),
    });
  } catch {
    // Do not block UX if cancel transition API is unavailable.
  }

  clearActionCards();
  setStepStatus('payment_preview', 'error', 'Cancelled');
  setStepStatus('payment', 'pending', 'Pending');
  setStepStatus('confirmation', 'pending', 'Pending');
  appendMessage('assistant', 'Payment cancelled. Returning to booking preview stage.');
}

roomCardsEl.addEventListener('click', async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  if (!target.classList.contains('select-room-btn')) return;

  const selectedRoomId = target.getAttribute('data-room-id');
  const selectedRoomType = target.getAttribute('data-room-type');
  if (!selectedRoomId) return;
  if (selectedRoomType) {
    bookingState.roomType = selectedRoomType;
  }

  showRoomResults(false);
  await openBookingFlow(selectedRoomId);
});

actionCardsEl?.addEventListener('click', async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const action = target.getAttribute('data-action');
  if (!action) return;

  if (action === 'confirm-booking') {
    await handleConfirmBooking();
    return;
  }

  if (action === 'pay-now') {
    await handlePayNow();
    return;
  }

  if (action === 'cancel-booking-preview') {
    await handleCancelBookingPreview();
    return;
  }

  if (action === 'cancel-payment-preview') {
    await handleCancelPaymentPreview();
  }
});

async function sendMessage() {
  const message = inputEl.value.trim();
  if (!message) return;

  appendMessage('user', message);
  inputEl.value = '';
  setBusy(true);

  try {
    showConciergeLoader('Your concierge is thoughtfully preparing your response...');
    parseBookingData(message);
    const data = await postChat(message);
    const shouldAutoSearchRooms = !bookingState.roomsLoaded && canSearchRooms();
    const assistantMessage = normalizeAssistantMessage(data);

    hideConciergeLoader();
    if (!(shouldAutoSearchRooms && (isInternalStageGuardMessage(assistantMessage) || isNoAvailabilityMessage(assistantMessage)))) {
      appendMessage('assistant', assistantMessage);
    }

    if (shouldAutoSearchRooms) {
      appendMessage('assistant', 'Checking live room availability for your dates now...');
      await loadRoomsAndRender();
    }
  } catch (error) {
    hideConciergeLoader();
    appendMessage('assistant', error.message || 'Failed to reach backend service.');
  } finally {
    setBusy(false);
    inputEl.focus();
  }
}

appendMessage('assistant', 'Welcome to Aurora Nexus Hotel. It is my pleasure to assist you today. I can help you book a room, explore our services, or handle support requests.');
appendMessage('assistant', 'May I have your name so I can prepare your reservation?');

if (sessionNoticeEl) {
  const startedAt = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  sessionNoticeEl.textContent = `Private session started at ${startedAt}. Refreshing this page starts a new session.`;
}

sendBtn.addEventListener('click', sendMessage);
inputEl.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    sendMessage();
  }
});

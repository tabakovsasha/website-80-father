(function() {
    'use strict';

    const CONFIG = { swipeThreshold: 120, wheelCooldown: 200, transitionDuration: 300, maxZoom: 4 };
    const viewer = document.getElementById('viewer');
    const viewport = document.getElementById('carousel-viewport');
    const track = document.getElementById('carousel-track');
    const slots = Array.from(document.querySelectorAll('.slide-slot'));
    const counter = document.getElementById('counter');
    const loader = document.getElementById('loader');
    const visitorId = localStorage.getItem('petr80_visitor_id') || crypto.randomUUID();
    localStorage.setItem('petr80_visitor_id', visitorId);
    const sessionId = crypto.randomUUID();

    const state = {
        slides: [], currentIndex: 0, totalSlides: 0, lastWheelTime: 0,
        isZoomed: false, zoomScale: 1, panX: 0, panY: 0,
        viewedSlides: new Set(), animating: false,
        drag: { active: false, mode: null, startY: 0, deltaY: 0, lastY: 0, lastX: 0, lastTime: 0, velocity: 0, pinch: false, pinchDistance: 0, pinchMidX: 0, pinchMidY: 0 }
    };

    function showLoader() { loader.style.display = 'block'; }
    function hideLoader() { loader.style.display = 'none'; }
    function updateCounter() { counter.textContent = state.totalSlides ? `${state.currentIndex + 1} / ${state.totalSlides}` : '0 / 0'; }

    function showNoImagesState() {
        updateCounter(); viewport.style.display = 'none'; loader.style.display = 'none';
        viewer.insertAdjacentHTML('beforeend', '<div class="status-message">Изображения отсутствуют</div>');
    }

    function showErrorState(message) {
        updateCounter(); viewport.style.display = 'none'; loader.style.display = 'none';
        viewer.insertAdjacentHTML('beforeend', `<div class="status-message error">${message}</div>`);
    }

    async function loadSlides() {
        try {
            const response = await fetch('/api/slides', { cache: 'no-store' });
            if (!response.ok) throw new Error('Failed to load slides');
            const data = await response.json();
            state.slides = data.slides || [];
            state.totalSlides = state.slides.length;
            updateCounter();
            return state.totalSlides > 0;
        } catch (error) {
            console.error(error); showErrorState('Не удалось загрузить слайды'); return false;
        }
    }

    function preloadImage(index) {
        const slide = state.slides[index];
        if (!slide) return;
        const image = new Image(); image.src = slide.path; image.loading = 'eager';
    }

    function preloadNeighbors() { preloadImage(state.currentIndex - 1); preloadImage(state.currentIndex + 1); }

    function sendAnalytics(path, payload) {
        const body = JSON.stringify(payload);
        if (navigator.sendBeacon) {
            const sent = navigator.sendBeacon(path, new Blob([body], { type: 'application/json' }));
            if (sent) return;
        }
        fetch(path, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, keepalive: true, body
        }).catch(() => {});
    }

    function recordVisit() {
        sendAnalytics('/analytics/visit', {
            visitor_id: visitorId,
            session_id: sessionId,
            total_slides: state.totalSlides
        });
    }

    function markSlideViewed(index) {
        const slide = state.slides[index];
        if (!slide || state.viewedSlides.has(slide.name)) return;
        state.viewedSlides.add(slide.name);
        sendAnalytics('/analytics/slide', {
            visitor_id: visitorId,
            session_id: sessionId,
            slide_id: slide.name,
            slide_index: index,
            total_slides: state.totalSlides
        });
    }

    function setSlot(slot, index) {
        slot.replaceChildren();
        const background = document.createElement('div');
        const image = document.createElement('img');
        background.className = 'slot-background'; image.className = 'slot-image'; image.alt = 'Slide';
        slot.append(background, image);
        const slide = state.slides[index];
        slot.dataset.index = slide ? String(index) : '';
        if (!slide) return;
        background.style.backgroundImage = `url("${slide.path}")`;
        image.src = slide.path;
    }

    function resetZoom() {
        state.isZoomed = false; state.zoomScale = 1; state.panX = 0; state.panY = 0;
        const image = slots[1].querySelector('.slot-image');
        if (image) image.style.transform = 'translate3d(0, 0, 0) scale(1)';
    }

    function applyZoomTransform() {
        const image = slots[1].querySelector('.slot-image');
        if (image) image.style.transform = `translate3d(${state.panX}px, ${state.panY}px, 0) scale(${state.zoomScale})`;
    }

    function viewportHeight() { return viewport.clientHeight || window.innerHeight; }
    function neutralPosition() { return -viewportHeight(); }

    function setTrackPosition(y, animate) {
        track.style.transition = animate ? `transform ${CONFIG.transitionDuration}ms cubic-bezier(0.22, 1, 0.36, 1)` : 'none';
        track.style.transform = `translate3d(0, ${y}px, 0)`;
    }

    function populateSlots() {
        setSlot(slots[0], state.currentIndex - 1);
        setSlot(slots[1], state.currentIndex);
        setSlot(slots[2], state.currentIndex + 1);
        setTrackPosition(neutralPosition(), false);
        resetZoom(); updateCounter(); preloadNeighbors();
    }

    function renderInitialSlide() {
        showLoader(); populateSlots(); markSlideViewed(state.currentIndex);
        const image = slots[1].querySelector('.slot-image');
        if (!image) return;
        image.addEventListener('load', hideLoader, { once: true });
        image.addEventListener('error', () => showErrorState('Не удалось загрузить изображение'), { once: true });
        setTimeout(hideLoader, 1000);
    }

    function validDirection(direction) { return direction > 0 ? state.currentIndex < state.totalSlides - 1 : state.currentIndex > 0; }

    function finishTransition(direction) {
        state.currentIndex += direction; state.animating = false; populateSlots(); markSlideViewed(state.currentIndex);
    }

    function animateTo(direction) {
        if (state.animating || !validDirection(direction)) return;
        state.animating = true;
        const destination = neutralPosition() + (direction > 0 ? -viewportHeight() : viewportHeight());
        const onEnd = (event) => {
            if (event.target !== track || event.propertyName !== 'transform') return;
            track.removeEventListener('transitionend', onEnd); finishTransition(direction);
        };
        track.addEventListener('transitionend', onEnd); setTrackPosition(destination, true);
    }

    function updateDrag(deltaY) {
        const direction = deltaY < 0 ? 1 : -1;
        const boundedDelta = validDirection(direction) ? deltaY : deltaY * 0.28;
        state.drag.deltaY = boundedDelta; setTrackPosition(neutralPosition() + boundedDelta, false);
    }

    function releaseDrag() {
        const deltaY = state.drag.deltaY;
        const direction = deltaY < 0 ? 1 : -1;
        const threshold = Math.max(CONFIG.swipeThreshold, viewportHeight() * 0.18);
        const fastEnough = Math.abs(state.drag.velocity) > 650;
        state.drag.active = false;
        if ((Math.abs(deltaY) >= threshold || fastEnough) && validDirection(direction)) animateTo(direction);
        else setTrackPosition(neutralPosition(), true);
    }

    function getTouchDistance(first, second) {
        const dx = first.clientX - second.clientX; const dy = first.clientY - second.clientY;
        return Math.sqrt(dx * dx + dy * dy);
    }

    function getTouchMidpoint(first, second) {
        const bounds = viewport.getBoundingClientRect();
        return {
            x: (first.clientX + second.clientX) / 2 - bounds.left,
            y: (first.clientY + second.clientY) / 2 - bounds.top
        };
    }

    function beginPinch(first, second) {
        const midpoint = getTouchMidpoint(first, second);
        state.drag.active = false;
        state.drag.mode = null;
        state.drag.pinch = true;
        state.drag.pinchDistance = getTouchDistance(first, second);
        state.drag.pinchMidX = midpoint.x;
        state.drag.pinchMidY = midpoint.y;
        setTrackPosition(neutralPosition(), false);
    }

    function setupTouch() {
        viewport.addEventListener('touchstart', (event) => {
            if (state.animating) return;
            if (event.touches.length === 2) {
                beginPinch(event.touches[0], event.touches[1]);
                return;
            }
            const touch = event.touches[0];
            state.drag.active = true;
            state.drag.mode = state.isZoomed ? 'pan' : 'carousel';
            state.drag.startY = touch.clientY;
            state.drag.lastY = touch.clientY;
            state.drag.lastX = touch.clientX;
            state.drag.lastTime = Date.now();
            state.drag.deltaY = 0;
            state.drag.velocity = 0;
        }, { passive: true });

        viewport.addEventListener('touchmove', (event) => {
            if (state.drag.pinch && event.touches.length === 2) {
                const distance = getTouchDistance(event.touches[0], event.touches[1]);
                const midpoint = getTouchMidpoint(event.touches[0], event.touches[1]);
                const previousScale = state.zoomScale;
                const nextScale = Math.max(1, Math.min(CONFIG.maxZoom, previousScale * distance / state.drag.pinchDistance));
                const ratio = previousScale ? nextScale / previousScale : 1;
                const centerX = viewport.clientWidth / 2;
                const centerY = viewport.clientHeight / 2;
                state.panX += (state.drag.pinchMidX - centerX - state.panX) * (1 - ratio) + midpoint.x - state.drag.pinchMidX;
                state.panY += (state.drag.pinchMidY - centerY - state.panY) * (1 - ratio) + midpoint.y - state.drag.pinchMidY;
                state.zoomScale = nextScale;
                state.isZoomed = nextScale > 1;
                state.drag.pinchDistance = distance;
                state.drag.pinchMidX = midpoint.x;
                state.drag.pinchMidY = midpoint.y;
                applyZoomTransform();
                event.preventDefault();
                return;
            }
            if (!state.drag.active || state.animating) return;
            const touch = event.touches[0]; const now = Date.now(); const dy = touch.clientY - state.drag.lastY; const dt = Math.max(1, now - state.drag.lastTime);
            state.drag.velocity = dy / dt * 1000;
            const previousX = state.drag.lastX;
            state.drag.lastY = touch.clientY; state.drag.lastX = touch.clientX; state.drag.lastTime = now;
            if (state.drag.mode === 'pan') { state.panY += dy; state.panX += touch.clientX - previousX; applyZoomTransform(); }
            else updateDrag(touch.clientY - state.drag.startY);
            event.preventDefault();
        }, { passive: false });

        viewport.addEventListener('touchend', (event) => {
            if (state.drag.pinch) {
                if (event.touches.length === 1) {
                    state.drag.pinch = false;
                    if (state.zoomScale <= 1) {
                        state.drag.active = false;
                        return;
                    }
                    const touch = event.touches[0];
                    state.drag.active = true;
                    state.drag.mode = 'pan';
                    state.drag.lastY = touch.clientY;
                    state.drag.lastX = touch.clientX;
                    state.drag.lastTime = Date.now();
                } else if (event.touches.length === 0) {
                    state.drag.pinch = false;
                }
                return;
            }
            if (!state.drag.active) return;
            if (state.drag.mode === 'pan') { state.drag.active = false; return; }
            releaseDrag();
        }, { passive: true });

        viewport.addEventListener('touchcancel', () => {
            state.drag.pinch = false;
            if (state.drag.mode === 'carousel') setTrackPosition(neutralPosition(), true);
            state.drag.active = false;
        }, { passive: true });
    }

    function navigate(direction) { if (!state.isZoomed && !state.animating && !state.drag.active) animateTo(direction); }

    function setupKeyboard() {
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && state.isZoomed) { resetZoom(); return; }
            if (state.isZoomed) return;
            if (event.key === 'ArrowRight' || event.key === 'PageDown' || event.key === 'ArrowDown') { event.preventDefault(); navigate(1); }
            else if (event.key === 'ArrowLeft' || event.key === 'PageUp' || event.key === 'ArrowUp') { event.preventDefault(); navigate(-1); }
        });
    }

    function setupWheel() {
        viewer.addEventListener('wheel', (event) => {
            const now = Date.now(); if (now - state.lastWheelTime < CONFIG.wheelCooldown || state.isZoomed) return;
            state.lastWheelTime = now; event.preventDefault(); navigate(event.deltaY > 0 ? 1 : -1);
        }, { passive: false });
    }

    window.addEventListener('resize', () => { if (!state.drag.active && !state.animating) setTrackPosition(neutralPosition(), false); });

    async function init() {
        if (!await loadSlides()) { showNoImagesState(); return; }
        recordVisit();
        renderInitialSlide(); setupTouch(); setupKeyboard(); setupWheel();
    }

    init();
})();

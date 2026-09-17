(function() {
    'use strict';

    // --- Конфигурация ---
    const CONFIG = {
        minScale: 1,
        maxScale: 4,
        swipeThreshold: 30,
        swipeCooldown: 300,
        wheelCooldown: 200,
        zoomDuration: 300,
        loaderDelay: 500
    };

    // --- DOM элементы ---
    const viewer = document.getElementById('viewer');
    const background = document.getElementById('background');
    const image = document.getElementById('image');
    const counter = document.getElementById('counter');
    const loader = document.getElementById('loader');

    // --- State ---
    let state = {
        currentIndex: -1,
        totalSlides: 0,
        isZoomed: false,
        isPanning: false,
        startX: 0,
        startY: 0,
        currentX: 0,
        currentY: 0,
        lastSwipeTime: 0,
        lastWheelTime: 0
    };

    // --- Данные ---
    let imagesData = [];

    // --- Инициализация ---
    async function init() {
        await loadManifest();

        if (state.totalSlides === 0) {
            showNoImagesState();
            return;
        }

        state.currentIndex = 0;
        updateCounter();
        preloadNeighbors();
        loadImage(0);
        setupEventListeners();
        applySafeAreaPadding();
    }

    // --- Загрузка манифеста ---
    async function loadManifest() {
        try {
            const response = await fetch('/data/images.json');
            if (!response.ok) throw new Error('Network error');
            const data = await response.json();
            imagesData = data.images || [];
            state.totalSlides = imagesData.length;
        } catch (error) {
            showErrorState('Не удалось загрузить манифест');
            console.error('Failed to load manifest:', error);
        }
    }

    // --- Показать "нет изображений" ---
    function showNoImagesState() {
        viewer.innerHTML = `<div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: #888;">Изображения отсутствуют</div>`;
        hideLoader();
    }

    // --- Показать ошибку ---
    function showErrorState(message) {
        viewer.innerHTML = `<div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: #f55;">${message}</div>`;
        hideLoader();
    }

    // --- Обновить счетчик ---
    function updateCounter() {
        if (state.totalSlides === 0) {
            counter.classList.add('hidden');
            counter.classList.remove('visible');
            return;
        }
        counter.innerText = `${state.currentIndex + 1} / ${state.totalSlides}`;
        counter.classList.remove('hidden');
        counter.classList.add('visible');
    }

    // --- Показать/скрыть loader ---
    function showLoader() { loader.style.display = 'block'; }
    function hideLoader() { loader.style.display = 'none'; }

    // --- Предзагрузка ---
    function preloadNeighbors() {
        state.preloadImages.forEach(id => { const img = document.getElementById(`preload-${id}`); if (img) img.remove(); });
        state.preloadImages.clear();
        if (state.totalSlides <= 1) return;
        const nextIndex = (state.currentIndex + 1) % state.totalSlides;
        const prevIndex = state.currentIndex - 1;
        if (prevIndex >= 0) preloadImage(prevIndex);
        preloadImage(nextIndex);
    }

    function preloadImage(index) {
        if (index < 0 || index >= state.totalSlides) return;
        const key = `slide-${index}`;
        if (state.preloadImages.has(key)) return;
        const img = document.createElement('img');
        img.style.display = 'none';
        img.src = imagesData[index].path;
        img.loading = 'lazy';
        document.body.appendChild(img);
        state.preloadImages.add(key);
    }

    // --- Загрузить изображение ---
    function loadImage(index) {
        if (index < 0 || index >= state.totalSlides) return;
        showLoader();
        state.currentIndex = index;
        updateCounter();
        const imgPath = imagesData[index].path;
        image.src = imgPath;

        image.onload = function() {
            background.src = imgPath;
            background.classList.add('visible');
            setTimeout(() => {
                background.classList.remove('visible');
                hideLoader();
                preloadNeighbors();
            }, CONFIG.loaderDelay);
        };

        image.onerror = function() {
            showErrorState(`Не удалось загрузить изображение ${index + 1}`);
            hideLoader();
        };
    }

    // --- Навигация ---
    function navigate(direction) {
        const newIndex = state.currentIndex + direction;
        if (newIndex < 0 || newIndex >= state.totalSlides) return;
        loadImage(newIndex);
    }

    // --- Свайпы ---
    function setupTouchEvents() {
        let touchStartX, touchStartY;

        viewer.addEventListener('touchstart', function(e) {
            touchStartX = e.touches[0].clientX;
            touchStartY = e.touches[0].clientY;
            state.isPanning = false;
        }, { passive: false });

        viewer.addEventListener('touchmove', function(e) {
            if (!touchStartX || !touchStartY) return;
            const deltaX = e.touches[0].clientX - touchStartX;
            const deltaY = e.touches[0].clientY - touchStartY;
            if (Math.abs(deltaX) > Math.abs(deltaY)) {
                e.preventDefault();
                state.isPanning = true;
            }
        }, { passive: false });

        viewer.addEventListener('touchend', function(e) {
            if (!touchStartX || !touchStartY) return;
            const deltaX = e.changedTouches[0].clientX - touchStartX;
            const deltaY = e.changedTouches[0].clientY - touchStartY;
            const absX = Math.abs(deltaX);
            const absY = Math.abs(deltaY);

            if (absY > absX && absY > CONFIG.swipeThreshold) {
                if (deltaY > 0) {
                    if (Date.now() - state.lastSwipeTime > CONFIG.swipeCooldown) {
                        state.lastSwipeTime = Date.now();
                        navigate(1);
                    }
                } else {
                    if (Date.now() - state.lastSwipeTime > CONFIG.swipeCooldown) {
                        state.lastSwipeTime = Date.now();
                        navigate(-1);
                    }
                }
            }

            touchStartX = null;
            touchStartY = null;
        });
    }

    // --- Mouse events ---
    function setupMouseEvents() {
        let wheelTimeout = null;

        viewer.addEventListener('wheel', function(e) {
            const now = Date.now();
            if (now - state.lastWheelTime < CONFIG.wheelCooldown) {
                e.preventDefault();
                clearTimeout(wheelTimeout);
                wheelTimeout = setTimeout(() => {}, CONFIG.wheelCooldown - (now - state.lastWheelTime));
                return;
            }
            state.lastWheelTime = now;

            if (e.deltaY > 0) navigate(1);
            else navigate(-1);
        }, { passive: false });

        document.addEventListener('keydown', function(e) {
            if (state.isZoomed) {
                if (e.key === 'Escape') { closeZoom(); e.preventDefault(); }
                return;
            }

            if (e.key === 'ArrowDown' || e.key === 'PageDown' || e.key === 'Right') {
                e.preventDefault(); navigate(1);
            } else if (e.key === 'ArrowUp' || e.key === 'PageUp' || e.key === 'Left') {
                e.preventDefault(); navigate(-1);
            }
        });

        let lastTapTime = 0;
        viewer.addEventListener('click', function(e) {
            const now = Date.now();
            if (now - lastTapTime < 300) {
                toggleZoom();
                lastTapTime = 0;
            } else { lastTapTime = now; }
        });
    }

    // --- Zoom ---
    let scale = 1;
    let isZoomed = false;

    function toggleZoom() {
        if (isZoomed) { closeZoom(); }
        else { openZoom(); }
    }

    function openZoom() {
        isZoomed = true;
        scale = 1;
        image.classList.add('zoomed');
        viewer.style.touchAction = 'none';
    }

    function closeZoom() {
        isZoomed = false;
        scale = 1;
        image.classList.remove('zoomed');
        viewer.style.touchAction = '';
        updateNavigationState();
    }

    // --- Запуск ---
    init().then(setupTouchEvents).then(setupMouseEvents);

    window.PetraViewer = { navigateNext: navigate, navigatePrev: function() { navigate(-1) }, toggleZoom: toggleZoom };
})();

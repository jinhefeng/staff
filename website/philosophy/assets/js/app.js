document.addEventListener('DOMContentLoaded', () => {
    console.log('Staff Philosophy Website Loaded.');

    // 滚动揭示 (Scroll Reveal)
    const observerOptions = {
        threshold: 0.1
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, observerOptions);

    document.querySelectorAll('section, .card').forEach(el => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(30px)';
        el.style.transition = 'all 0.8s cubic-bezier(0.23, 1, 0.32, 1)';
        observer.observe(el);
    });

    // 卡片 3D 悬浮感 (Tilt Effect Simulation)
    const cards = document.querySelectorAll('.card');
    cards.forEach(card => {
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            const centerX = rect.width / 2;
            const centerY = rect.height / 2;
            const rotateX = (y - centerY) / 10;
            const rotateY = (centerX - x) / 10;
            
            card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-10px) scale(1.02)`;
        });

        card.addEventListener('mouseleave', () => {
            card.style.transform = `perspective(1000px) rotateX(0deg) rotateY(0deg) translateY(0) scale(1)`;
        });
    });

    // 模拟梦境机制的动态 LOG
    const consoleLog = (msg) => {
        console.log(`%c[CORE_ENGINE]%c ${msg}`, 'color: #7000ff; font-weight: bold', 'color: #a0a0a0');
    };

    const sysLogs = [
        '记忆机制: 联邦沙箱物理隔离校验中...',
        '学习机制: 梦境提纯启动，异步更新 [SOUL.md] 配置...',
        '引用机制: 话题链回溯成功，锁定 L3 级历史上下文',
        '响应机制: 探测到 Master 闲暇期，准备主动回禀工单进展',
        '裁决机制: 定时任务 [Daily_Report] 执行前置环境校验中...'
    ];

    setInterval(() => {
        consoleLog(sysLogs[Math.floor(Math.random() * sysLogs.length)]);
    }, 4000);

    // 机制卡片联动特效
    document.querySelectorAll('.mechanism-card').forEach(card => {
        card.addEventListener('mouseenter', () => {
            card.style.borderColor = 'var(--accent-color)';
            card.style.boxShadow = '0 0 30px var(--accent-glow)';
        });
        card.addEventListener('mouseleave', () => {
            card.style.borderColor = 'var(--border-color)';
            card.style.boxShadow = 'none';
        });
    });
});

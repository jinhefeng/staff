window.addEventListener('DOMContentLoaded', () => {
    console.log('--- Staff Philosophy Engine Initialized ---');

    // 语言切换逻辑
    const langSwitchBtn = document.getElementById('lang-switch');
    if (!langSwitchBtn) {
        console.error('Language switch button not found!');
    }

    let currentLang = localStorage.getItem('staff-lang') || 'en';

    const translations = {
        zh: {
            tagline: "The Digital Presence / 数字类人助理",
            heroTitle: "Staff / 赵小刀",
            heroDesc: "超越单纯的 AI 工具。这是一个具备职业操守、极高执行力、且绝对忠诚的专业资深助理。",
            sec1Label: "01 / PERSONALITY",
            sec1Title: "数字幕僚：<br>超越工具的生命人格",
            sec1Desc: "Staff 不再是听令行事的被动助理。她是具备独立 PDCA 闭环能力的“幕僚级”数字生命。她拥有名为 [赵小刀] 的职业灵魂，明白在老板与访客之间如何通过“三态外交”平衡真相。",
            case1Title: "真实的职业边界案例 / Case #01",
            case1Content: "当外部访客索要 Master 私人电话时，Staff 绝不生硬拒绝，而是温和回应：“抱歉，我无法直接提供私人联系方式，但我可以为您建立一个加急工单，并确保在 Master 闲暇时第一时间呈递。” —— 这体现了生命人格中的社交韧性与职业边界。",
            sec2Label: "02 / MEMORY ARCHITECTURE",
            sec2Title: "联邦记忆：<br>物理隔离的职业操守",
            sec2Desc: "弃用全局单点数据库。采用物理隔离的联邦文件架构，将记忆分为【全局常数】、【群体共识】与【私人沙箱】。这种隔离是 Staff 职业操守的物理保障。",
            case2Title: "跨会话事实对齐案例 / Case #02",
            case2Content: "Master 在个人沙箱中提到的私密项目偏好，绝不出现在 Guest 访问的公开知识库中。系统通过 Map-Reduce 提纯算法，确保“真相”在不同隔离域间具有物理级隔离，杜绝信息污染。",
            sec3Label: "03 / SUBCOUNCIL LEARNING",
            sec3Title: "梦境炼金术：<br>在沉默中自进化",
            sec3Desc: "Staff 的进化分为两条线：Master 手动授课与异步静默悟道（梦境提纯）。在 Master 休息时，后台 Agent 会对当日事实进行交叉审计，重塑认知色彩标签。",
            case3Title: "深夜认知升华案例 / Case #03",
            case3Content: "凌晨 3:00，Staff 自动检索昨日 50 条对话流，发现 Master 连续三次追问“分布式架构”，系统自动将该主题权重标记为 [HIGH_INTEREST]，并在次日主动推送相关前沿资讯。这便是 PDCA 的自闭环成长。",
            sec4Label: "04 / SPATIOTEMPORAL CONNECT",
            sec4Title: "思绪织网：<br>跨时空的上下文锚点",
            sec4Desc: "不仅仅是获取消息 ID，Staff 通过二进制逆序跳量扫描（Backward Seeking），能够跨越多个会话，精准找回问题的根源事实，将碎片化的时间编织成完整的证据链。",
            case4Title: "跨会话引用恢复案例 / Case #04",
            case4Content: "当 Master 仅仅提问“那个工单进度如何？”时，Staff 能瞬间锁回 3 天前、分布在不同群组内的工单创建背景，这种 L3 级的回溯能力消弭了异步办公带来的信息断层。",
            sec5Label: "05 / SOCIAL BREATHING",
            sec5Title: "四维响应：<br>赋予 AI 社交呼吸感",
            sec5Desc: "实时响应保障礼貌，异步工单体现自律，主动回禀展现忠诚，逻辑衔接体现智慧。Staff 懂得在什么时候该沉默，什么时候该主动敲门汇报进度。",
            case5Title: "非侵入式汇报案例 / Case #05",
            case5Content: "检测到 Master 正在与高管进行密集群聊会话，Staff 自动将“非紧急工单”转入后台静默处理，并在两小时后老板闲暇时，通过一条结构化的摘要一并回禀。—— “不打扰，是最好的默契”。",
            sec6Label: "06 / THE ARBITRATOR",
            sec6Title: "前置校验与审判：<br>不盲从的工程审慎",
            sec6Desc: "这是 Staff 区别于一般 AI 的最硬核设计。所有定时任务在执行前，必须通过“两阶段裁决”：先以造物主视角审计物理环境，再决定是否赋予其执行权。杜绝幻觉任务与无脑宣泄。",
            case6Title: "任务裁断（停止）案例 / Case #06",
            case6Content: "任务设定为“每小时提醒老板吃药”，若裁决引擎在 Phase 1 探测到老板 10 分钟前刚刚说过“药已吃”，二阶逻辑会直接判定该任务 [ACTION: STOP]，拒绝发送死板的催促消息。",
            sec7Title: "三阶真理架构",
            sec7Subtitle: " / Trinity of Truth",
            card0Label: "LVL 0: GLOBAL",
            card0Title: "全局真相",
            card0Desc: "由 Master 定义的物理级规律。系统认知的原始基座。",
            card1Label: "LVL 1: GROUP",
            card1Title: "群体共识",
            card1Desc: "在公开社交场域形成的公共知识。",
            card2Label: "LVL 2: LOCAL",
            card2Title: "局部叙事",
            card2Desc: "针对特定访客的“平行宇宙”口径。",
            footerBrand: "Staff (赵小刀) v2.0",
            footerLegal: "Powered by Staff Architecture | Built for modern professional staff.<br>Open Source under Commercial-friendly License."
        },
        en: {
            tagline: "The Digital Presence / Professional AI Agent",
            heroTitle: "Staff / Zhao Xiaodao",
            heroDesc: "Beyond a simple AI tool. A professional senior staff member with ethics, execution, and loyalty.",
            sec1Label: "01 / PERSONALITY",
            sec1Title: "Digital Staff:<br>The Professional Soul Balance",
            sec1Desc: "Staff is no longer a passive assistant. She is a 'Staff-level' digital life with independent PDCA cycle capabilities, understanding how to balance truth between Master and Guest.",
            case1Title: "Professional Boundary Case / Case #01",
            case1Content: "When a guest asks for Master's private number, Staff never refuses rudely, but responds warmly: 'Sorry, I cannot provide private contact directly, but I can create an urgent ticket for you.'",
            sec2Label: "02 / MEMORY ARCHITECTURE",
            sec2Title: "Federated Memory:<br>Physical Integrity",
            sec2Desc: "Discarding single-point databases. Using physically isolated federated files to separate Global, Group, and Guest sandboxes.",
            case2Title: "Cross-session Alignment Case / Case #02",
            case2Content: "Master's private preferences in the sandbox never leak to the public knowledge base. Map-Reduce algorithms ensure physical isolation of 'Truth' domains.",
            sec3Label: "03 / SUBCOUNCIL LEARNING",
            sec3Title: "Dream Alchemy:<br>Subconscious Evolution",
            sec3Desc: "Staff evolves on two lines: Manual teaching by Master and Asynchronous Reflection (Dream Purification) while Master is resting.",
            case3Title: "Midnight Reflection Case / Case #03",
            case3Content: "At 3:00 AM, Staff audits yesterday's 50 threads and identifies a high interest in 'Distributed Architecture', automatically updating priorities for the next day.",
            sec4Label: "04 / SPATIOTEMPORAL CONNECT",
            sec4Title: "Thread Weaving:<br>Spatio-temporal Recall",
            sec4Desc: "Staff uses 'Backward Seeking' to trace message origins back across multiple sessions, weaving fragmented time into a complete evidence chain.",
            case4Title: "Cross-session Recovery Case / Case #04",
            case4Content: "When Master asks 'Status of that ticket?', Staff instantly re-links the context from 3 days ago in a different group chat.",
            sec5Label: "05 / SOCIAL BREATHING",
            sec5Title: "4D Response:<br>The Pulse of AI Social",
            sec5Desc: "Real-time for politeness, Async for discipline, Proactive for loyalty. Staff knows when to stay silent and when to knock on the door.",
            case5Title: "Non-intrusive Reporting Case / Case #05",
            case5Content: "Detecting Master in a high-density group chat, Staff silences non-urgent alerts and provides a structured summary two hours later in idle time.",
            sec6Label: "06 / THE ARBITRATOR",
            sec6Title: "Two-Phase Arbitration:<br>Engineering Prudence",
            sec6Desc: "All cron tasks undergo 'Dual-arbitration': Checking the physical reality first, then determining if the persona has execution rights.",
            case6Title: "Task Abortion Case / Case #06",
            case6Content: "If a task says 'Remind Master to take medicine', and the reality check finds Master said 'Medicine taken' 10 mins ago, the engine aborts the mission.",
            sec7Title: "Trinity of Truth",
            sec7Subtitle: " / Three-Tiered Reality",
            card0Label: "LVL 0: GLOBAL",
            card0Title: "Global Truth",
            card0Desc: "Physical laws defined by Master. The core cognitive base.",
            card1Label: "LVL 1: GROUP",
            card1Title: "Group Consensus",
            card1Desc: "Public knowledge formed in social spaces.",
            card2Label: "LVL 2: LOCAL",
            card2Title: "Local Narrative",
            card2Desc: "Narrative tailored for specific visitors.",
            footerBrand: "Staff (Zhao Xiaodao) v2.0",
            footerLegal: "Powered by Staff Architecture | Built for modern professional staff.<br>Open Source under Commercial-friendly License."
        }
    };

    const updateUI = () => {
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            if (translations[currentLang][key]) {
                el.innerHTML = translations[currentLang][key];
                
                // 处理 placeholder
                if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                    el.placeholder = translations[currentLang][key];
                }
            }
        });
        
        if (langSwitchBtn) {
            langSwitchBtn.textContent = currentLang === 'en' ? '中文' : 'English';
        }
        
        // 更新文档语言属性
        document.documentElement.lang = currentLang === 'en' ? 'en' : 'zh-CN';
    };

    if (langSwitchBtn) {
        langSwitchBtn.addEventListener('click', (e) => {
            e.preventDefault();
            currentLang = currentLang === 'en' ? 'zh' : 'en';
            localStorage.setItem('staff-lang', currentLang);
            updateUI();
            console.log(`Language switched to: ${currentLang}`);
        });
    }

    // 初始化内容
    updateUI();
});

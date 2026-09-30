# 突破自身想象力！Claude Oups 5.5纯靠一句Prompt做出10款逆天游戏



- 作者：行运设计师

- 原文：https://www.toutiao.com/article/7690894754007106111/



作者：伯衡君

世界那么大，我带你去看看

把AI写代码这件事说烂了，但"用AI从零构建可玩游戏"还是新鲜事。

Claude Opus 5.5出来之后，一批创作者用它做了不少让人意外的东西：有纸雕风格的开放世界、有三.js网页版蜘蛛侠、有烧了1874美元token费做的热带岛屿。这不是Demo展览，是完整可玩的体验。

这篇盘点这10个作品，顺便聊聊AI游戏开发的真实水位——哪些能看、哪些能玩、哪些还只是玩具。

说实话，半年前提"AI能写代码做游戏"，大多数人还会翻白眼。但Opus 5.5这一波把门槛又往下拉了一截。不是靠某个单一的神级Prompt，而是靠一个系统性的工作流：先描述玩法，再生成代码，然后调试、修复、迭代。

这10个游戏有个共同点：每个都是纯文本Prompt驱动生成的。没有美术资产包，没有现成模板。AI从空项目开始，自己搭框架、写逻辑、调参数。有的做完只能跑几分钟，有的能打开新存档玩上几小时。

想明白这一层，这个榜的单位就不只是"好玩程度"，而是"AI独立开发能力的边界"在哪里。

PaperWorld是用纸艺风格做的开放世界探索游戏。你控制一只纸飞机在充满热气球和彩色建筑的世界里飞行。UI里能看到时间切换、天气控制、相机角度调整——这些功能都是AI自己加进去的。

它的美术风格很讨巧：纸雕质感天然掩盖了3D建模的粗糙感，低多边形加上纸张纹理，反而有种手绘绘本的味道。但玩起来会发现，飞行物理和操控精度还有明显提升空间。

这算是AI游戏开发里一个聪明的方向：用风格优势掩盖技术短板。与其硬做写实画面，不如选一个"本来就该看起来不真实"的美术风格，AI的缺陷反而成了特色。

伯衡君此前特别为此编写了一篇详细的文章，对此做过介绍，请参看《限制你的只剩想象力！1句提示词做开放世界，单文件塞下整个游戏》。

Willowmere是个俯视视角的生活模拟游戏，类似星露谷物语那种路线。你在一个小镇里建房、种地、和NPC互动，底部有经典的RPG技能栏。

亮点在于AI做对了一个很多独立游戏都做不好的事情：交互节奏。游戏的节奏不紧不慢，建房子需要时间，作物需要等待，NPC的行为有规律可循。这些设计决策不是来自提示词里的"像星露谷"三个字，而是AI自己摸索出来的。

不过AI在任务系统和剧情深度上明显弱了很多。整个游戏更像是一个可以逛的"空壳"，缺乏让人持续玩下去的目标感。适合截图发朋友圈，不太适合认真玩。

Koi Pond Garden是个纯粹的观赏类模拟——你在一个池塘里养锦鲤，看着它们游来游去。水的反射、鱼鳞的光泽、荷叶的漂浮，视觉效果做得相当细致。

这个项目的价值不在于"好玩"，而在于"能做出来"。用自然光、流体模拟、粒子效果做一个平静的池塘，传统游戏开发需要专门的水面着色器和物理模拟团队。AI一个人全包了，而且完成度不算低。

适合碎片时间挂机，或者当作桌面背景。但它也暴露了AI游戏开发的一个现状：AI很擅长做"氛围型"游戏，不太擅长做"挑战型"游戏。前者靠美术和音效撑着，后者靠数值设计和平衡性。

The Road That Forgets是个节奏驾驶游戏。屏幕上会出现音符提示你转向，视觉上是一条不断向前延伸的道路。你 steering 穿过音符，错过就会扣分或结束。

核心机制不复杂，但执行得相当精致。音符的节奏感和道路的延伸感配合得很好，有一种冥想式的体验。视觉风格也是极简的，干净的3D渲染配上柔和的色调。

这类"小而美"的游戏正是AI擅长做的——体量小、机制清晰、不需要大量资产。但对更复杂的游戏类型，比如RPG或RTS，AI目前还力不从心。

Three.js Spider-Man是个基于浏览器的3D蜘蛛侠Demo。你能看到蜘蛛侠在摩天大楼之间摆荡、跑墙、跳跃。完全在浏览器里运行，不需要下载任何东西。

Three.js本身是个轻量级的3D引擎，在浏览器里跑出这种流畅度的3D动作游戏，是个不错的技术展示。但说实话，玩法深度有限——主要是跑图体验，战斗和任务系统基本没有。

这个项目更重要的意义在于展示了"可访问性"：不用安装包、不用显卡、打开网页就能玩。这对独立游戏开发者是个值得参考的方向，尤其适合做原型验证。

Far Cry 3 Clone是个第一人称射击游戏，场景设定在热带岛屿上。你手持步枪，站在木码头上，旁边停着摩托艇，四周是清澈的蓝色海水。

AI在环境和氛围营造上做得不错：阳光穿透树叶的光线、水面的波纹反射、植被的密度，这些都达到了可玩游戏的水平。但FPS的核心——射击手感和敌人AI——明显不够成熟。敌人像是站桩靶子，没有战术行为。

不过换个角度看，一个AI从Prompt生出来的完整FPS原型，已经比很多人手动写出来的Demo要完整了。进步是肉眼可见的。

Mumbai & Bengaluru是个以印度城市为背景的驾驶游戏，你开着auto rickshaw（自动人力车）在城市里穿梭。低多边形的美术风格，画面里能看到的路牌。

这个游戏有意思的地方在于地域特色。不是又一个欧美都市，而是真实的印度街景——路牌、建筑风格、车辆类型，都带着南亚风情。AI能从Prompt里理解并还原这种文化细节，本身就说明了它在语义理解上的进步。

驾驶手感比较粗糙，但作为一个城市探索游戏，它提供了一种独特的视角：在数字世界里体验另一个文化的日常生活。

Spider-Man: Symbiote是这10个游戏里视觉效果最接近"商业游戏"的一个。你控制穿着黑色共生体战衣的蜘蛛侠在城市屋顶间奔跑，UI显示着任务目标和等级通知，场景在"Financial District"。

3D建模精度、光影效果、角色动画流畅度，都明显高于榜单其他作品。AI在这个项目里展现了对复杂3D场景和角色动作的理解能力——不是简单贴个蜘蛛侠贴图，而是真正理解了角色的运动方式。

当然，距离真正的3A还有差距。NPC行为、任务系统、关卡设计，这些深度内容AI还没办法独立完成。但作为AI生成游戏的天花板，这个水平已经足够令人印象深刻。

Inkwave是个类似《喷射战士》的第三人称射击游戏。画面里到处都是明亮的紫色墨水，UI显示着计时器、玩家图标和小地图，玩家刚被"淘汰"。

这个项目最厉害的地方在于"风格识别"——AI从Splatoon的玩法描述中，理解了"墨水覆盖地面"这个核心机制，并忠实还原了。虽然画面不如原版精致，但游戏的核心循环已经成型。

AI游戏开发的一个关键突破就在这里：它能理解"玩法概念"，而不只是"美术风格"。写代码容易，理解"为什么这个游戏好玩"更难。Inkwave证明AI开始能跨过这道门槛。

The $1,874 Island是这次榜单的冠军。你走在热带海滩的木栈道上，夕阳把海面染成金色，远处是茂密的热带植被。右侧有个"DETAIL CHECKLIST"，列出了各种环境效果的技术指标。

1874美元不是游戏成本，是token费——用来生成这个游戏的Claude API调用费用。这意味着AI在这个项目上花费了巨大的计算资源：反复迭代场景、调整光影、优化性能。每一个画面细节都是钱烧出来的。

这个项目最大的价值不在于游戏本身有多好玩，而在于它证明了：只要有足够的token预算，AI能造出接近商业水准的图形体验。代价确实不低，但方向是对的。

看完这10个游戏，一个清晰的趋势浮现出来了：AI目前最擅长的是"风格独特、体量不大"的游戏类型。纸雕世界、锦鲤池塘、节奏驾驶——这些不需要复杂数值平衡的游戏，AI能做出令人惊喜的效果。

但短板也很明显：任务系统、经济系统、AI敌人行为，这些深度玩法AI还搞不定。商业游戏最值钱的部分——让玩家持续回来的设计——恰恰是AI最薄弱的环节。

所以我的看法是：别指望AI独立做出一款完整的商业游戏。但让它帮你做原型、生成美术资产、搭建基础框架，这个能力已经非常成熟了。接下来的几年，AI不会取代游戏开发者，但会用AI的游戏开发者会取代不用AI的。

人工智能在游戏创制领域的效能正呈指数级攀升，尤其在氛围感内容搭建与核心玩法原型验证层面具备天然优势。

当前其核心短板集中于深度系统设计维度，具体体现为任务架构、经济模型、智能体行为逻辑等模块的搭建能力尚存明显不足。

定价1874美元的“AI游戏岛”案例已证实，数字token本身就是直接的生产要素，而可支配预算的量级，本质上决定了AI游戏开发的天花板边界。

延伸阅读：Claude Opus 5.5的官方文档、各游戏项目的GitHub仓库、Three.js官方教程。如果你想自己动手试试，建议从Koi Pond Garden这种小体量项目开始。

以上，既然看到这里了，如果觉得不错，随手点个赞、收藏、转发三连吧，如果想第一时间收到最新黑科技，敬请关注行运设计师。

谢谢你看我的文章，我们，下次再见。



## 图片

- https://p3-sign.toutiaoimg.com/tos-cn-i-axegupay5k/e9157683b8c345f28f8463e8fc9d682e~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=UZW1%2FyvYAeA9JWElXe1B0C4Rj24%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/070bcec94ead44488e3f08a641b1d50e~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=R%2BFYCuGvY4xl9zTFVPUJEIaC4Ew%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/071c80f7484746b9a1b5a19132b87c93~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=obwDIkffNMm4EdcvB7vhvTEFpOo%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/bc0dc08ac48148279729c941c036f894~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=xmOd%2F7nH%2BxY3QEMbhH2v3nJkL90%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/986a49d9a19249f6808c466cb007cb5b~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=pfQiwm2t7%2Bd74zlUNfJiQEerLFY%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/5d46d063b90641b6bbb0f68a47f84742~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=Hs54poKDjgMMOPc8pI%2FsF%2FOcA1s%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/e5c5a51cb93f4eeebffff1f8c67775e7~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=QlBV3OfLrKALRAzXSTJZwF9sTJ0%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/a192016bc3ed4a49a12ed0a4084f4e72~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=kxljXbXuwcY1lyGmbFKkCLGKtn0%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/410dc016c47f4d44be9fb14992d81ea2~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=Y2JO7USws1IG9Rlm7aJL12VaLX8%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/d866d4a0c29a4926b057e344f8093e23~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=4vkcokW%2FntzrekYPH85TA4d1D5k%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/978930cba3b5461987e7c5036503eebc~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=wypMHCPTic42cgtCozs054Jg%2FAc%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/430ebcdfcc5244bf9e12aa6d470cd3f7~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=jJCIopVacmG3WK9gpw65hB2QjCY%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/c6a47eeb134b439d94e894c2cf91467c~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=0f%2B4KDWvqNzqouXwWC5CSlfH0uc%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/70ab9d1231b4492ea6955c7af4932ca0~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=xt0eRy5gcXc1fMWzoV3zIaezag0%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/ef92d6f88a51497a97a9fb7d6103c807~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=mfnGVj98u%2FADrYXXIUbWLczGSD0%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/2459e4a3d2f6435690267af3b6663207~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=qyRn3kW%2Bbopvjx4RTuq5FCMucMg%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/c83acc9017e84da480723a17e1ef1420~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=3c3r7bZ2nlNM7FlpwSt%2BtAQ9Pmc%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/461f3e36a60b47dbb1fc37e5a283a733~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=LPjuP7c3eNHiJ%2Bj0oM6RYCQAKLk%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/169b4c9cc65a4410b669ff2ae923bd02~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=5qmm1j4m5t8u2uk4ktBMq0SF7BQ%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/8123ce6fdd984f32b4f5d59423ffc50f~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=65M%2FwjxEQo20HEf9lkW%2Bgl7EXmc%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/3e9422651b6c4b69919c567edaed3e72~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=EJR2SFWaO6ZUbWNe3eciUd2j1kw%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/61e9d8b4235b482cb1348f6f08986ca4~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=tNIBSjSf%2FDnptVRnebLQBrwFUd8%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/b1c9a6bb38544800a96ad18352f72628~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=HrvCRIJFXCNmgAAxQYfwCySDFYQ%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/1354863150914b71ae2793062f1d14d6~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=yG6F%2Bm2LRk7z%2FQHfmCLSditnbBM%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/91b3656e3f1345a2aac8daf5ead9f50c~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=doPhs%2FiNzaeYpAWvm5xDc9FOaQA%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/c1f209553ad349efbbd912a7c759e572~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=5V5uJgGrJKixF0A9SSvjmz500gw%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/d11832f6d39f40d89b1ce5e4aa613f9f~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=aF7ebfOYaCE2djrwPyHMhapTAsY%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/94087f960503402db476c7ee6e09ade9~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=XhYjE6hL0joO8Gf6wfbRAP9%2BKxI%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/93b85da905b94fa1b76efe760c21e30a~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=hJaJoCPYWMKSojo3tp5DyleuSH0%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/eee2e6ba52544ff1955e39f56348c8c7~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791387142&x-signature=Ypp4%2Fv5DAU7ciScloLLvJ%2FH%2F2iY%3D
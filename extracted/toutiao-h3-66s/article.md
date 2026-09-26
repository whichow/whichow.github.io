# 烧了3亿Token，跑通超高质量视频绘画Skill，我决定开源了！



- 作者：AI维克兹

- 原文：https://www.toutiao.com/article/7676021805278183972/



最近，熬了两晚上。

2天时间，烧了3亿 Token，只为做一件事， 视频Skill 。

看到效果的那一刻，我决定把这个skill，开源了！

因为，我觉得很多人都可能会用到。

skill 名称： create-whiteboard-video ，搭配上Codex，可以一次性生成一条完整的白板手绘视频出来。

目前已经上传到了GitHub。

https://github.com/Weikezi-AI/create-whiteboard-video

https://aizyd.net/lab/skills/create-whiteboard-video

今年是马年，那么我们就做个小马过河的视频。

先看视频的效果， 后面我再教大家如何使用这个视频Skill。

我们开始只需要给 Codex @出来这个技能，然后告诉它：

“

帮我做一个《小马过河》的视频出来

经过几分钟以后，它就做出来了 100 秒的白板手绘动画视频。

说实话，我是没想到，我第一次尝试做开源skill，可以出来这种效果。

这条视频一共 8 幕，包含普通话女声旁白和字幕。

成片、源图、音频、字幕、单幕视频、工程文件和质检报告几乎全包包含了。

最让我满意的地方，不是最终视频能完美播放了，是这个过程它已经实现了流水生产线。

通过这个 Skill 可以无限生产出各类绘画视频，如果你觉得这个Skill 还不够好，也可以基于这个 Skill 继续优化。

每一步知道该做什么，关键结果会停下来让我们确认，发现问题可以只返工当前环节，不需要把前面全部推倒重来。

下面是关于skill的使用过程

由于之前的测试我已经指定过目录了，所以这次，我发出任务后，先问我，是否把素材、临时文件、运行环境、工程文件和最终成片全部放进这个目录：

我回复“确认”后，它才开始建立项目。

当然我加进来的这一步，是因为我对这些skill生成的文件存放位置特别敏感。

这个动作看起来有点慢，但是可以有效预防 C盘爆满，素材散落 的问题。

确认目录后，这次项目的全部文件都被收进了同一个文件夹。

后面无论暂停、继续、替换某张图，还是单独重做某一幕，都能从这个项目里往下走。

《小马过河》大家都很熟，但要做成这种动画手绘视频，其实是不能把整篇故事直接塞进去的。

需要Codex或者其他AI工具根据skill，先写一版适合儿童观看的口播稿，保留故事最重要的部分，然后自动规划，第一次先把故事拆成了 6 幕。

这里有个问题，其实有些问答和动作被挤在同一个场景里，画面承担的信息太多。

于是它自动重新校准成 8 幕：

这版顺序就清楚多了。

每一幕只有一个主要动作，上一幕的结果也会自然推动下一幕。

分镜确定以后，它没有马上批量生成 8 张图，而是先做第 1 幕作为画风测试。

第一张图出来后，整体方向其实还不错。

暖黄色纸张、手绘线条、少量水彩质感，小马和妈妈的角色也很适合儿童故事。

但仔细一看，小马出问题了！

它为了表现“挥手告别”，给小马多画了一条前腿，画面里实际出现了五条腿！！

说真的，我好久没遇到这种类似于“6 根手指”的出图问题了，

这要是给小孩子吓坏了可不行，必须重做。

修正版做好以后，就可以作为整条视频的角色和画风参考。

其余场景都沿用同一匹小马、同一个橙色麦袋和同一套暖色绘本风格。

我很喜欢这个流程。

先用一张图试错，确认方向以后，就开始自动批量生成，比 8 张全部做完后一起返工省事得多。

画风确定后，Codex 开始逐幕制作剩余图片。

让我感到激动的是，每张图出来后，还会继续检查动物数量、四肢结构、麦袋位置和故事逻辑。

比如这里：

第 6 幕需要同时出现小马、老牛和松鼠。

第一版虽然动物数量正确，小马却用前蹄托着下巴思考，还是明显的人类手势。

Codex 没有让这张图进入工程，自动修正。

修正版让四蹄全部落地，只用歪头、视线和耳朵表达思考。

这些调整没有涉及复杂参数。

我只需要判断画面哪里不对，Codex 负责修改对应场景，再把合格版本放回项目。

最终的 8 幕画面是这样的：

角色、麦袋、道路、河流和磨坊之间形成了连续关系，8 张图单独看能成立，连起来也能讲清完整故事。

图片完成后，Skill 继续生成普通话女声旁白，听感更接近儿童故事。

实际旁白时长约为 100 秒，原来的分镜估算接近 115 秒。

如果直接沿用估算，画面中间会出现明显等待，字幕和场景也容易错位。

所以它按照真实旁白重新计算了 8 幕时长，让每个场景跟着声音结束，而不是让音频硬塞进事先猜好的时间里。

字幕也重新整理成完整句子。

素材和时间轴全部锁定后，Skill 把 8 张图、旁白和字幕样式一起展示出来，让我做最后一次确认。

我选择把字幕直接烧录进画面，然后回复确认生成。

收到确认后，8 幕进入正式渲染。

这次是 Skill 当前默认的整图斜向扫描： 画面整体从左上推进到右下，每一条笔触从左下画向右上，轮廓和铺色沿着同一条路径完成。

固定的手部画笔会跟着真实落墨位置移动。

8 幕全部渲染成功后，Skill 把场景拼接起来，加入旁白和字幕，生成了这一版完整的视频。

《小马过河》之外，我还用同一套 Skill 做出了《小红帽》。

视频一共 10 幕，时长约 2 分多钟，测试下来依旧稳定产出。

虽然两条视频的内容不一样，但它们走的是同一条生产路径：

确认目录 → 故事与分镜 → 画风测试 → 批量素材 → 旁白与字幕 → 素材确认 → 渲染 → 合成 → 质检。

对我来说，它已经可以正式作为一条白板视频流水线来使用了。

虽然它还需要人看分镜、挑画面和做最后判断，但重复劳动已经被大幅接管。

人负责把控方向，Agent 负责把这条长流程继续跑完。

当然，后续我还会持续优化迭代这个Skill,帮我做出更高质量的视频。

从一句“帮我做个《小马过河》”，到最后拿到完整视频项目，这次测试给出的答案已经很明确了。

这条视频流水线，跑通了。

这个Skill，也是我花了大量的心血，熬夜两晚跑出来的。

希望对你有所帮助。

谢谢，你看我的文章。

如果觉得不错，随手点个赞、在看、转发三连吧，如果想第一时间收到推送，也可以给我个星标⭐～谢谢你看我的文章，我们，下次再见。

我是维克兹，前程序员、现创业者。

目前主要关注 AIGC 人工智能，资深燃劲AI鼓励师，希望分享好用的AI工具，AI应用技能，激发你对AI的好奇。



## 图片

- https://p3-sign.toutiaoimg.com/tos-cn-i-axegupay5k/3d5988ea8144414fb1c3d0891f4a8fa2~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791060168&x-signature=tYnVrcWnAP725CelC1f9fZFLH%2BM%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/5217a4e327ac43929814722cc4b8d0b6~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791060168&x-signature=gov6J8FF0hT%2FpfG%2Fdf2jMJ57PFE%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/850caf7fd2c743ee9ad1f22f96c87e93~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791060168&x-signature=fH5wJ0x3f1bzO6jaGsTYGzyQdFo%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/36f9b9ab3ac44f6faf6be6800810fbcd~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791060168&x-signature=%2Bf%2Foyrrv%2FTeW3Vuko5Vv3RFORpk%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/67165cc617fe4a3bbdf50018cfc33f80~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791060168&x-signature=DFqanUXY6%2FPooXFj2iLpDr%2BXqWQ%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/9360d856ccb9479aa28d0b0b5294e61e~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791060168&x-signature=yYsu71xicjOjclJU7VRkJv11H70%3D

- https://p6-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/fd09d775c9194f2bbb8d6223bf385188~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791060168&x-signature=lOjRXpn6db3nefTo8s5p4h6kMgY%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/ff410717ba5c4a9093d28eb6d15282a3~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791060168&x-signature=vzhv52y42gIyT55TnsEso3s8ORA%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/b262dbe57ccd4093ac531d1a7bb2868e~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791060168&x-signature=34hTmHtnNFD8dTRrfNkCYQfFDFA%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/f061a225f84244e59de41a51c0a74155~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791060168&x-signature=%2BgCUqbQcLhKYDd9R2adkexzeXoA%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/b2a68475584d45a3a65a7c4ab13e9afc~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791060168&x-signature=xpHx%2BiOgtOBWRFohbtXK2YkLATA%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/1a8dfa206743436abc31ca3ab0ef4365~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791060168&x-signature=MOlKo1IoqTenssKOu5iaVAIYkXc%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/636d551015fe4607b9c9a4b94a50f7ba~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791060168&x-signature=rWvI4Sdn%2BOGWQb%2FwKqly4nhYs1w%3D

- https://p6-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/48edb916db554756bed299fa06b54c7a~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791060168&x-signature=lt0%2FFBtyuBxA4oLldif6auqovrA%3D

- https://p11-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/500cb63aff52456d8abf86405ff41e0e~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791060168&x-signature=YCR%2BlYKOzCxWGd6M%2B%2BKdWKI81kk%3D

- https://p3-sign.toutiaoimg.com/tos-cn-i-6w9my0ksvp/c647be589eb9420e8d1ad97d7da95a50~tplv-tt-large.image?_iz=30575&lk3s=06827d14&x-expires=1791060168&x-signature=Kje8J98gBmLbsgDh%2FBAUJp%2Fkq2U%3D
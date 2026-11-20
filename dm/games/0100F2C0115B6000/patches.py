# The Legend of Zelda: Tears of the Kingdom (0100F2C0115B6000): the rewriter's patches of this game's own builds. dm/tools/patch_nso.py loads every profile's patches.py and applies those of a module's NSO build ID;
# CUTS, OBS and FRAME_STEP as described there ("Registered patches"). Patches of Nintendo SDK module builds are in dm/tools/sdk_patches.py
import struct
from nso_asm import ADRP, B, NOP, STP_PRE

# Tears of the Kingdom picks a present interval each frame (main+0x2db174: 2 = 30 fps, 3 under load) and steps its game time by 60 / fps (int fps at timing +0x50, read at main+0x2daa54
# and main+0x3e562c). The stub replaces that logic: int fps = 60 / step, and the float fps (timing +0x24, unused, per masagrator's FPSLocker config for this build, which found the
# sites) the same, which the consumers read. Until the host has decided a step (the first frames) the step is the measured frame time (timing frame +0xd8, 19.2 MHz
# ticks), clamped to [1 / cap, 1 / 15 s]; game time that ran ahead after a short frame (the "lead", at most 0.25 s; totk-mobile) is paid back by later frames. Prerendered movies hold 30 (the host's movie flag, state +4, hle_movie.c
# dm_movie_hz), the D-pad menu fade starts at full rate (FPSLocker's fix at main+0x1fbc80) and the swapchain argument at main+0xbe14a8 becomes 1 as in FPSLocker
def stub(ctx, step, read1, read2, fade, swap, view):
    """The frame step at the frame-step function (step), the two readers of the integer fps (read1, read2), the D-pad menu fade (fade), the swapchain argument (swap) and
    the view render size (view): each patched at its own offsets"""
    here, emit, fs_site, fs_put, FS_STATE_OFF = ctx.here, ctx.emit, ctx.site, ctx.put, ctx.state
    # frame step (replaces ldrb w9,[x0,#0x58], the first instruction after the prologue)
    fs_site(step + 0x18, '09604139')
    start = here(); emit(ADRP(16, here(), FS_STATE_OFF))
    for w in (0xbd400200,   # ldr s0,[x16]           target fps
              0x1e202008,   # fcmp s0,#0.0
              0x54000640,   # b.eq off (+50)        target 0: original path
              0xb9402202,   # ldr w2,[x16,#0x20]     step in vsyncs
              0x340001a2,   # cbz w2,elapsed (+13)   not decided yet: by the measured frame time
              0x1e230041,   # ucvtf s1,w2
              0x1e27d003,   # fmov s3,#30.0
              0x1e211872,   # fdiv s18,s3,s1
              0x1e322a52,   # fadd s18,s18,s18       fps = 60 / step
              0xbd002412,   # str s18,[x0,#0x24]     float fps
              0x52800785,   # mov w5,#60
              0x1ac208a5,   # udiv w5,w5,w2
              0xb9005005,   # str w5,[x0,#0x50]      integer fps
              0xf9401a04,   # ldr x4,[x16,#0x30]
              0x8b224084,   # add x4,x4,w2,uxtw
              0xf9001a04):  # str x4,[x16,#0x30]     vsyncs stepped
        emit(w)
    emit(B(here(), step + 0x110))                                       # the original epilogue
    for w in (0xf9406c22,   # elapsed: ldr x2,[x1,#0xd8]  last frame time in 19.2 MHz ticks
              0x9e630041,   # ucvtf d1,x2
              0x529f0003,   # mov w3,#0xf800
              0x72a02483,   # movk w3,#0x124,lsl #16 (19,200,000)
              0x1e630062,   # ucvtf d2,w3
              0x1e621821,   # fdiv d1,d1,d2          elapsed seconds
              0xb9400604,   # ldr w4,[x16,#4]        movie flag
              0x1e27d003,   # fmov s3,#30.0
              0x7100009f,   # cmp w4,#0
              0x1e201c60,   # fcsel s0,s3,s0,ne      cap = movie ? 30 : target
              0x1e22c000,   # fcvt d0,s0
              0x1e6e1003,   # fmov d3,#1.0
              0x1e601864,   # fdiv d4,d3,d0          shortest step 1 / cap
              0x1e65d005,   # fmov d5,#15.0
              0x1e651865,   # fdiv d5,d3,d5          longest step 1 / 15
              0xfd400606,   # ldr d6,[x16,#8]        lead
              0x1e663827,   # fsub d7,d1,d6
              0x1e6448e7,   # fmax d7,d7,d4
              0x1e6558e7,   # fmin d7,d7,d5          step = clamp(elapsed - lead)
              0x1e6728c6,   # fadd d6,d6,d7
              0x1e6138c6,   # fsub d6,d6,d1          lead += step - elapsed
              0x2f00e410,   # movi d16,#0
              0x1e7048c6,   # fmax d6,d6,d16
              0x1e6a1011,   # fmov d17,#0.25
              0x1e7158c6,   # fmin d6,d6,d17         lead in [0, 0.25]
              0xfd000606,   # str d6,[x16,#8]
              0x1e671872,   # fdiv d18,d3,d7         fps = 1 / step
              0x1e624252,   # fcvt s18,d18
              0xbd002412,   # str s18,[x0,#0x24]     float fps
              0x1e380245,   # fcvtzs w5,s18
              0xb9005005,   # str w5,[x0,#0x50]      integer fps
              0xfd400e13,   # ldr d19,[x16,#0x18]
              0x1e672a73,   # fadd d19,d19,d7
              0xfd000e13):  # str d19,[x16,#0x18]    game seconds stepped
        emit(w)
    emit(B(here(), step + 0x110))                                       # the original epilogue
    emit(0x39416009); emit(B(here(), step + 0x1c))                     # off: ldrb w9,[x0,#0x58]; back
    fs_put(step + 0x18, [B(step + 0x18, start)], 'frame step from the host in whole vsyncs, by elapsed time until it has decided one (state page target fps; 0 = original interval logic)')
    # the two readers of the integer fps: float fps when on; the scvtf a few instructions later moves into the stub (s0 is not touched in between)
    for site, cvt, r in ((read1 + 0x34, read1 + 0x4c, 19), (read2 + 0x4c, read2 + 0x58, 22)):
        fs_site(site, struct.pack('<I', 0xbd425000 | r << 5).hex()); fs_site(cvt, '00d8215e')
        start = here(); emit(STP_PRE(16, 17, 31, -16)); emit(ADRP(16, here(), FS_STATE_OFF))
        for w in (0xb9400211,                # ldr w17,[x16]
                  0x34000071,                # cbz w17,off (+12)
                  0xbd422400 | r << 5,       # ldr s0,[xR,#0x224]  float fps
                  0x14000003,                # b done (+12)
                  0xbd425000 | r << 5,       # off: ldr s0,[xR,#0x250]  integer fps
                  0x5e21d800,                # scvtf s0,s0
                  0xa8c147f0):               # done: ldp x16,x17,[sp],#16
            emit(w)
        emit(B(here(), site + 4))
        fs_put(site, [B(site, start)], 'game step reads the float fps (original integer fps and scvtf when off)')
        fs_put(cvt, [NOP], 'scvtf moved into the stub at the load')
    # D-pad menu fade (w8 is overwritten right after the site)
    fs_site(fade + 0x130, '0820201e0a04081f')
    start = here(); emit(ADRP(8, here(), FS_STATE_OFF))
    for w in (0xb9400108, 0x340001a8,       # ldr w8,[x8]; cbz w8,off (+52)
              0x1e202028, 0x54000101,       # fcmp s1,#0.0; b.ne go
              0x785fa308, 0x7100151f, 0x540000a1,   # ldurh w8,[x24,#-6]; cmp w8,#5; b.ne go
              0x785f8308, 0x7100151f, 0x54000041,   # ldurh w8,[x24,#-8]; cmp w8,#5; b.ne go
              0x1e2e1008,                   # fmov s8,#1.0
              0x1f08040a, 0x1e202008, 0x14000003,   # go: fmadd s10,s0,s8,s1; fcmp s0,#0.0; b end
              0x1e202008, 0x1f08040a):      # off: the original fcmp s0,#0.0; fmadd s10,s0,s8,s1
        emit(w)
    emit(B(here(), fade + 0x138))
    fs_put(fade + 0x130, [B(fade + 0x130, start), NOP], 'D-pad menu fade starts at full rate under fractional steps (FPSLocker)')
    # swapchain argument (x16 is dead before the bl that follows)
    fs_site(swap + 0x1a4, '61a24039')
    start = here(); emit(ADRP(16, here(), FS_STATE_OFF))
    for w in (0xb9400210, 0x34000070, 0x52800021, 0x14000002, 0x3940a261):   # ldr w16,[x16]; cbz w16,off; mov w1,#1; b end; off: ldrb w1,[x19,#0x28]
        emit(w)
    emit(B(here(), swap + 0x1a8))
    fs_put(swap + 0x1a4, [B(swap + 0x1a4, start)], 'swapchain argument 1 when on (FPSLocker)')
    # Render scale (state +0x10, float written by the loader: DM_RENDER_SCALE, 1.0 by default). main+0xd5c24 sizes each view: screen size x the view's scale (5/6 for the scene: 1600x896
    # docked) x the dynamic-resolution multiplier, clamped to 8..16384 and floored to the view's alignment. The stub multiplies both extents by the factor (s6, w8 and the flags are dead
    # at main+0xd5cc0: s6 is set to 8.0 right after); any factor but 1.0 also replaces the dynamic multiplier (main+0xd5d80) with 1, so the size is fixed. 1.0 = bit-exact original
    fs_site(view + 0x9c, '08d0a8524008251e6108241e0401271e'); fs_site(view + 0x15c, '062940bd')
    start = here(); emit(ADRP(8, here(), FS_STATE_OFF))
    for w in (0xbd401106,   # ldr s6,[x8,#0x10]   render scale
              0x1e250840,   # fmul s0,s2,s5       (original)
              0x1e240861,   # fmul s1,s3,s4       (original)
              0x1e2020c8,   # fcmp s6,#0.0
              0x5400006d,   # b.le skip (+12)     not set
              0x1e260800,   # fmul s0,s0,s6
              0x1e260821,   # fmul s1,s1,s6
              0x52a8d008,   # skip: mov w8,#0x46800000 (original)
              0x1e270104):  # fmov s4,w8          (original)
        emit(w)
    emit(B(here(), view + 0xac))
    fs_put(view + 0x9c, [B(view + 0x9c, start)], 'view render size x the host render scale (1.0 = original)'); ctx.render_scale = 1
    start = here(); emit(0xbd402906); emit(ADRP(8, here(), FS_STATE_OFF))   # ldr s6,[x8,#0x28] (original: the dynamic multiplier); x8 is dead after it
    for w in (0xbd401107,   # ldr s7,[x8,#0x10]
              0x1e2e1010,   # fmov s16,#1.0
              0x1e3020e0,   # fcmp s7,s16
              0x54000080,   # b.eq done (+16)     scale 1: the game's dynamic resolution
              0x1e2020e8,   # fcmp s7,#0.0
              0x5400004d,   # b.le done (+8)      not set
              0x1e204206):  # fmov s6,s16         a fixed scale: no dynamic multiplier
        emit(w)
    emit(B(here(), view + 0x160))
    fs_put(view + 0x15c, [B(view + 0x15c, start)], 'dynamic resolution only at render scale 1.0')

def matched_frame_step(ctx):
    """Any build whose six functions match: all or nothing, as the readers without the step (or the step without them) run the game at the wrong speed (the locator prints a
    red line for the one not found)"""
    o = ctx.others
    parts = [o.get(k) for k in ('game step reader 1', 'game step reader 2', 'menu fade', 'swapchain argument', 'view render size')]
    if None in parts: return
    stub(ctx, ctx.base, *parts)
    if ctx.base == 0x2db174: screen_shape(ctx)   # 1.4.3's own addresses (its frame-step function there)

def screen_shape(ctx):
    """Screen shape (DM_SCREEN_ASPECT, Breath of the Wild 1.9.0's patches.py ported to 1.4.3): a screen taller than 16:9 (the iPhone Duo's, about 1.43:1) gets a picture of its
    own shape. State +0x48 u32 output height, +0x4c u32 layout height, +0x50 float layout height, +0x54 u32 site mask (DM_SCREEN_ASPECT_SITES), +0x58 float screen ratio
    (0 = off), +0x5c float k = (16/9) / ratio, +0x60 float tolerance, +0x74..+0x7c the HUD camera's projection, +0xfc / +0x100 the last 64 widened fovys (loader.c).
    Work in progress: the camera is ported; which of the size sites is the screen's own size is being found site by site with the mask (a site is off while its bit is 0)"""
    here, emit, fs_site, fs_put, FS_STATE_OFF = ctx.here, ctx.emit, ctx.site, ctx.put, ctx.state
    # The game's 1920x1080 and 1280x720 pairs (movk xN,#1080 or #720,lsl #32): each takes the host's height while its bit of state +0x54 is set and the host set one.
    # x16 is free at every site (checked: written or unused before the next call or return; 1.4.3 main+0x8c81f4 reads it and is left out)
    OUT, LAY = 0xb9404a10, 0xb9404e10   # ldr w16,[x16,#0x48] / #0x4c
    def taller_bit(site, reg, bit, load, why):
        orig = 0xf2c00000 | (0x438 if load == OUT else 0x2d0) << 5 | reg
        fs_site(site, struct.pack('<I', orig).hex())
        start = here(); emit(orig)
        emit(ADRP(16, here(), FS_STATE_OFF))
        emit(0xb9405610); emit(0x36000000 | bit << 19 | 5 << 5 | 16)   # ldr w16,[x16,#0x54]; tbz w16,#bit,back (+5)
        emit(ADRP(16, here(), FS_STATE_OFF))
        for w in (load, 0x34000050, 0xb3607e00 | reg):   # ldr w16,[x16,#off]; cbz w16,+8 (0: the game's size); bfi xN,x16,#32,#32 (the pair's height)
            emit(w)
        emit(B(here(), site + 4))
        fs_put(site, [B(site, start)], why)
    for bit, (site, reg, load, why) in enumerate((
            (0xbdb584, 8, OUT, '1920x1080 beside NvInitializeGraphics (graphics init)'),
            (0xd404f0, 9, OUT, '1920x1080 at +0xb68 (display object, setup)'),
            (0xd404e0, 11, LAY, '1280x720 at +0xb70 (display object, setup)'),
            (0xd40d50, 8, OUT, '1920x1080 at +0xb68 (display object, init)'),
            (0xd40d5c, 8, LAY, '1280x720 at +0xb70 / +0xb78 (display object, init)'),
            (0xd081fc, 8, OUT, '1920x1080 at +0x260 (object 0xd080c4)'),
            (0xd08214, 8, LAY, '1280x720 at +0x268 (object 0xd080c4)'),
            (0xedfe90, 25, OUT, '1920x1080 render target descriptor'),
            (0xe64104, 10, OUT, '1920x1080 object default'),
            (0x1eba890, 10, OUT, '1920x1080 object default'),
            (0x6ee938, 10, LAY, '1280x720'),
            (0x8c3fe8, 10, LAY, '1280x720'),
            (0xd47068, 8, LAY, '1280x720'),
            (0x2880b3c, 24, LAY, '1280x720'),
            (0x2880e34, 8, LAY, '1280x720'))):
        taller_bit(site, reg, bit, load, f'screen shape site {bit}: {why} → the host\'s height')
    # The field of view, as in Breath of the Wild: sead::PerspectiveProjection (fovy +0xa0, sin / cos / tan of half of it +0xa4 / +0xa8 / +0xac, aspect +0xb0) takes a fovy of
    # 2 atan(tan(fovy / 2) x k) for a view of the screen's ratio, so 16:9's sides stay in view with more above and below. The same code as Breath of the Wild's at setFovy_
    # (1.4.3 main+0x27d53f8), the constructor (+0xc02694) and set() (+0xd4275c); the body is Breath of the Wild's (its patches.py fov_stub), tanf / atanf through 1.4.3's PLT
    # The scene cameras' aspect: unlike Breath of the Wild, whose projections took the view's ratio, two camera builders (1.4.3 main+0x9a1bc, +0x218eeb8) load a 16:9
    # constant ([main+0x2d02534]) as the aspect for the sead::PerspectiveProjection constructor and set(), so the taller view was drawn with a 16:9 projection (stretched
    # vertically; iPhone Duo, first trial). They take the screen's ratio (state +0x58) instead while it is on; the fovy stubs below then widen them. x16 is free up to the bl
    def cam_aspect(site):
        fs_site(site, '033545bd')   # ldr s3,[x8,#0x534]
        start = here(); emit(0xbd453503); emit(ADRP(16, here(), FS_STATE_OFF))
        for w in (0xb9405a10, 0x34000050, 0x1e270203):   # ldr w16,[x16,#0x58]; cbz w16,+8 (off); fmov s3,w16
            emit(w)
        emit(B(here(), site + 4))
        fs_put(site, [B(site, start)], 'scene camera aspect: the screen\'s ratio instead of 16:9 while the screen shape is on')
    cam_aspect(0x9a1bc); cam_aspect(0x218eeb8)
    # Every place that sets a projection's aspect (+0xb0, with its changed flag +8), Ocarina of Time's way (its patches.py wide_view): a value near 16:9 takes the screen's
    # ratio (state +0x58) while the screen shape is on. Near, not exact: the game cameras' own parameter is 1.7778, not 1920/1080 to the bit (Ocarina's finding; an exact test
    # changed nothing on the phone, second trial), so the test is (bits - bits(16/9 - 0.0098)) >> 18 == 0 (16/9 - 0.0098 to about + 0.02). Each site counts its passes at state
    # +0x130 + 4 x index, the widened ones at +0x124 and keeps the last other value at +0x128: the host logs them every 300 frames while +0x110 is set ("wide view camera",
    # hle_nvn.c), so the log tells which sites the game runs. Kinds: 'store' str sN,[xB,#0xb0]; 'const' str wN,[xB,#0xb0] of the 16:9 constant; 'arg' fmov s8,s3 at the
    # entry of set() and the constructor (the aspect argument, which their fovy stubs compare). x16 / x17 and the flags' users: checked free at each (no flag is written)
    def cnt(off): return (0xb9400211 | (off // 4) << 10, 0x11000631, 0xb9000211 | (off // 4) << 10)   # ldr w17,[x16,#off]; add w17,w17,#1; str w17,[x16,#off]
    def aspect_site(k, site, kind, n, b, why):
        orig = {'store': 0xbd00b000 | b << 5 | n, 'const': 0xb900b000 | b << 5 | n, 'arg': 0x1e204068}[kind]
        apply = 0x1e270228 if kind == 'arg' else 0xb900b011 | b << 5   # fmov s8,w17 / str w17,[xB,#0xb0]
        fs_site(site, struct.pack('<I', orig).hex())
        start = here(); emit(ADRP(16, here(), FS_STATE_OFF))
        for w in cnt(0x130 + 4 * k): emit(w)
        if kind == 'const':
            for w in (0xb9405a11, 0x34000011 | 6 << 5, apply) + cnt(0x124): emit(w)   # ldr w17,[x16,#0x58]; cbz w17,the original (+6); the ratio; widened += 1
            emit(B(here(), site + 4)); emit(orig); emit(B(here(), site + 4))
        else:
            for w in (0x1e260011 | n << 5, 0x52800010 | 0x4e39 << 5, 0x72a00010 | 0x3fe2 << 5,   # w17 = the value's bits; w16 = bits(16/9 - 0.0098)
                      0x4b100231, 0x53127e31, 0x35000011 | 9 << 5):                          # (w17 - w16) >> 18 != 0: not 16:9 (+9: other)
                emit(w)
            emit(ADRP(16, here(), FS_STATE_OFF))
            for w in (0xb9405a11, 0x34000011 | 9 << 5, apply) + cnt(0x124): emit(w)   # the ratio, 0: the original (+9); apply; widened += 1
            emit(B(here(), site + 4))
            emit(ADRP(16, here(), FS_STATE_OFF)); emit(0x1e260011 | n << 5); emit(0xb9012a11)   # other: +0x128 = the value
            emit(orig); emit(B(here(), site + 4))
        fs_put(site, [B(site, start)], f'screen shape: a 16:9 projection aspect set here takes the screen\'s ratio (site {k}: {why})')
    for k, (site, kind, n, b, why) in enumerate((
            (0x628c7c, 'store', 0, 20, 'the game camera\'s own parameter +0x140'),
            (0xd4fdc, 'store', 0, 24, 'view update, from camera parameters +0x218'),
            (0xb43468, 'store', 0, 23, 'from parameters +0x68'),
            (0x4e9830, 'store', 0, 24, 'a viewport\'s ratio'),
            (0x1ff04f8, 'store', 0, 8, 'a viewport\'s ratio'),
            (0x253fbb4, 'store', 0, 8, 'a viewport\'s ratio'),
            (0xd42748, 'arg', 3, 0, 'sead::PerspectiveProjection::set'),
            (0xc02618, 'arg', 3, 0, 'sead::PerspectiveProjection constructor'),
            (0x89ddac, 'const', 8, 21, 'a 16:9 constant with a 1280x720 viewport'),
            (0x22dc2c0, 'const', 8, 23, 'a 16:9 constant with a 1280x720 viewport'))):
        aspect_site(k, site, kind, n, b, why)
    TANF, ATANF = 0x2bb7470, 0x2bb7480
    FOV_BODY = (None, 0xbd405a01, 0x1e202028, 0x540003e0, 'ratio', 0x1e213842, 0x1e20c042, 0xbd406203, 0x1e232040, 0x5400032a,
                0xb940a269, 0x9104020a, 0x5280080b, 0xb840454c, 0x6b09019f, 0x54000260, 0x7100056b, 0x54ffff81,
                'half_to_s0', 'tanf', None, 0xbd405e01, 0x1e210800, 'atanf', 's0_to_half', 0x1e202800, 0xbd00a260,
                None, 0xb940fe0b, 0x1200156c, 0x1100056b, 0xb900fe0b, 0x9104020a, 0xbc2c5940, 'half_to_s0')
    def fov_stub(site, orig, aspect_word, half_to_s0, s0_to_half):
        fs_site(site, orig)
        start = here()
        for w in FOV_BODY:
            if w is None: emit(ADRP(16, here(), FS_STATE_OFF))
            elif w == 'tanf': emit(B(here(), TANF) | 0x80000000)
            elif w == 'atanf': emit(B(here(), ATANF) | 0x80000000)
            else: emit({'ratio': aspect_word, 'half_to_s0': half_to_s0, 's0_to_half': s0_to_half}.get(w, w))
        emit(B(here(), site + 4))
        fs_put(site, [B(site, start)], 'sead::PerspectiveProjection fovy widened for a view of the screen\'s ratio (more above and below, 16:9 sides), stored widened')
    fov_stub(0x27d53f8, '0041201e', 0xbd40b262, 0x1e204100, 0x1e204008)   # setFovy_: ratio at [x19,#0xb0], half in s8
    fov_stub(0xc02694, '0041201e', 0xbd40b262, 0x1e204100, 0x1e204008)    # constructor: aspect stored at +0xb0 before, half in s8
    fov_stub(0xd4275c, '2041201e', 0x1e204102, 0x1e204120, 0x1e204009)    # set(): ratio still in s8, half in s9
    # The HUD camera's matrix (doUpdateMatrix, 1.4.3 main+0x27d5438): Breath of the Wild's stub, the same leaf code
    fs_site(0x27d5444, '0188552d')
    start = here(); emit(0x2d558801); emit(ADRP(16, here(), FS_STATE_OFF))   # ldp s1,s2,[x0,#0xac] (tan, aspect)
    for w in (0xb9412209, 0x11000529, 0xb9012209,   # matrices built += 1 (state +0x120, logged as "projections built"; w9 is free in this leaf)
              0xbd405a10, 0x1e202208, 0x54000320, 0xbd407611, 0x1e313851, 0x1e20c231, 0xbd407a12, 0x1e322220, 0x5400026a,   # ratio on; aspect 16:9
              0x2d534811, 0x1e2e1013, 0x1e332220, 0x540001e1, 0xbd407e13, 0x1e332240, 0x54000181,                          # near 1, far 10000
              0x1e204202,                                                                                                  # aspect = ratio
              0xb940a009, 0x9104020a, 0x5280080b, 0xb840454c, 0x6b09019f, 0x540000a0, 0x7100056b, 0x54ffff81,             # fovy widened already: done
              0xbd405e11, 0x1e310821):                                                                                     # tan x k
        emit(w)
    emit(B(here(), 0x27d5448))
    fs_put(0x27d5444, [B(0x27d5444, start)], 'PerspectiveProjection matrix: the HUD camera (16:9, near 1, far 10000) takes the screen\'s ratio and a widened vertical angle')

# Placed by the functions they patch, on any build that keeps all six (checked on 1.4.3, 2026-11-09: rewritten byte-identical to the build entry it had until then,
# FRAME_STEP of build 277178b7…, at main+0x2db174, +0x2daa20, +0x3e55e0, +0x1fbb50, +0xbe1304 and +0xd5c24)
MATCH_FRAME_STEP = {'main': [
    {'name': '60 fps frame step and render scale', 'size': 664, 'fingerprints': ['568aa53f9c6cfb840d42343952d0607b8f591bd03371888da644cbff748c16a1'],   # 1.4.3 main+0x2db174
     'stub': matched_frame_step,
     'others': {'game step reader 1': {'size': 856, 'fingerprints': ['7bdc3508ead27be8afedb9ae131f5b84787fd8554014d7a84cffa445dfff560a']},   # main+0x2daa20
                'game step reader 2': {'size': 2076, 'fingerprints': ['52c8386b11109040366aa12d2bc2495893b58acd0eab2b1e8fbd603654ca0814']},   # main+0x3e55e0
                'menu fade': {'size': 956, 'fingerprints': ['ae7e76274536fcebaad185597bf35b805cc25290e73893eb1759627154390244']},   # main+0x1fbb50
                'swapchain argument': {'size': 2236, 'fingerprints': ['06b4cd07e8d1b00273acd822e623077bb88368e4b85183f7ee5d0f279fee1c35']},   # main+0xbe1304
                'view render size': {'size': 504, 'fingerprints': ['dbff3ac3e5a0cef5da139724cdb066bbff275cbe476afe82b1025246cbd7c18f']}}},   # main+0xd5c24
]}

# How general each patch is and could be (dm/tools/docs_patches.py "Binding", listed in docs/agents/game-patches.md): what, its binding now, the loosest it could have (goal),
# purpose, why; blocked or kept: why the gap stays open (cannot close yet, or left open on purpose); checked: what was checked on game files (else a judgement)
BINDING = [
    {'what': '60 fps frame step and render scale', 'now': 'game', 'goal': 'game', 'purpose': 'frame rate',
     'why': "the game's own timing object, found by its six functions' fingerprints on any build that keeps them; no engine sibling shares the code (BotW, SMO, MK8D, ACNH, "
            'Splatoon 2 / 3, Kirby, Mario Party, Ocarina, Smash, Metroid Dread, Origami King: no exact match, 2026-11-09)',
     'checked': '1.4.3 main: one function of each fingerprint; the rule rewrites it byte-identical to its former build entry (2026-11-09)'},
]

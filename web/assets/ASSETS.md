# Monitoring robot

`agent-robot.png` — generated with the built-in image_gen tool from the user's
attached robot image, with transparency enabled. The original was retained at
the tool's generated-images location. No API keys were used for generation.

Final prompt:

> Use case: background-extraction. Edit target: the user's last attached image,
> the white and blue friendly robot on a pale blue background. Extract ONLY that
> exact robot as a clean full-body cutout on genuinely transparent background.
> Preserve its identity, glossy white armor, black visor, blue joints, pose and
> all limbs. Remove the entire pale background and floor/shadow. Center robot
> tightly framed with small transparent padding. No text, no new objects.
> Output a PNG asset for a website animated agent.

The galaxy is rendered procedurally in `monitor-galaxy.js`, using the user's
galaxy reference for its spiral arms, blue starlight, and warm central glow.
Robot float, orbit, galaxy rotation and outward light pulses are code animations.

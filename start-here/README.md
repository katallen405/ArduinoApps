# 😀 Start Here

<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>lelib API Reference</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, -apple-system, sans-serif; color: #fff; background: #111; padding: 2rem; max-width: 900px; margin: 0 auto; line-height: 1.6; }
  h1 { font-size: 22px; font-weight: 500; color: #fff; }
  h2 { font-size: 18px; font-weight: 500; color: #fff; }
  .hero { display: flex; align-items: center; gap: 14px; margin-bottom: 2rem; }
  .hero-icon { width: 44px; height: 44px; border-radius: 8px; background: #2a2a2a; display: flex; align-items: center; justify-content: center; flex-shrink: 0; font-size: 22px; }
  .hero p { font-size: 14px; color: #aaa; margin-top: 4px; }
  pre { background: #1e1e1e; border: 1px solid #333; border-radius: 8px; padding: 12px 16px; font-family: monospace; font-size: 13px; overflow-x: auto; margin: 0 0 2rem; color: #ff6b6b; }
  .intro-note { font-size: 13px; color: #aaa; margin-bottom: 2rem; line-height: 1.6; }
  .section { margin-bottom: 2.5rem; }
  .section-header { display: flex; align-items: center; gap: 10px; margin-bottom: .75rem; padding-bottom: .5rem; border-bottom: 1px solid #2a2a2a; }
  .badge { font-size: 11px; font-weight: 500; padding: 3px 8px; border-radius: 20px; }
  .badge-motor { background: #1a2e24; color: #6ee7b7; }
  .badge-controller { background: #1e1a2e; color: #a78bfa; }
  .badge-sensor { background: #2e2010; color: #fcd34d; }
  .desc { font-size: 14px; color: #bbb; margin-bottom: 1rem; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  thead tr { background: #1a1a1a; }
  th { text-align: left; padding: 8px 12px; font-weight: 500; font-size: 11px; color: #666; letter-spacing: .04em; text-transform: uppercase; border-bottom: 1px solid #2a2a2a; }
  td { padding: 9px 12px; border-bottom: 1px solid #1e1e1e; vertical-align: top; color: #fff; }
  tr:last-child td { border-bottom: none; }
  code { font-family: monospace; font-size: 12px; background: #1e1e1e; border: 1px solid #333; border-radius: 4px; padding: 1px 5px; white-space: nowrap; color: #ff6b6b; }
  .ret { font-size: 12px; color: #aaa; font-family: monospace; }
  .color-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; margin-top: .75rem; }
  .color-swatch { border-radius: 8px; overflow: hidden; border: 1px solid #2a2a2a; }
  .swatch-color { height: 32px; }
  .swatch-label { padding: 6px 8px; font-size: 12px; font-weight: 500; background: #1a1a1a; color: #fff; }
  .color-section-label { font-size: 11px; font-weight: 500; color: #666; letter-spacing: .04em; text-transform: uppercase; margin: 1.25rem 0 .5rem; }
</style>
</head>
<body>

<div class="hero">
  <div class="hero-icon">⚙️</div>
  <div>
    <h1>lelib API reference</h1>
    <p>LEGO Education wrapper — automatic retry logic &amp; friendlier method names</p>
  </div>
</div>

<pre>import lelib
from lelib import singleMotor, doubleMotor, colorSensor, controller</pre>

<p class="intro-note">All four classes share the same <code>connect()</code> signature and retry behavior: up to 5 attempts, 1-second delay between retries if the device reports "not ready", raising a <code>ConnectionError</code> on final failure.</p>

<div class="section">
  <div class="section-header">
    <h2>singleMotor</h2>
    <span class="badge badge-motor">motor</span>
  </div>
  <p class="desc">Controls a single LEGO motor. Extends <code>legoeducation.SingleMotor</code>.</p>
  <table>
    <thead><tr><th>Method</th><th>Parameters</th><th>Description</th></tr></thead>
    <tbody>
      <tr><td><code>connect(card_color, card_serial)</code></td><td><code>card_color</code> – Bluetooth card color<br><code>card_serial</code> – card serial number</td><td>Connects with up to 5 retries.</td></tr>
      <tr><td><code>spin(rotations=1)</code></td><td><code>rotations</code> <em>int/float, default 1</em></td><td>Runs the motor for the given number of rotations (converts to degrees internally).</td></tr>
      <tr><td><code>stop()</code></td><td>—</td><td>Stops the motor immediately.</td></tr>
      <tr><td><code>set_speed(speed)</code></td><td><code>speed</code> – speed value</td><td>Sets the motor speed.</td></tr>
      <tr><td><code>run()</code></td><td>—</td><td>Runs the motor continuously until stopped.</td></tr>
    </tbody>
  </table>
</div>

<div class="section">
  <div class="section-header">
    <h2>doubleMotor</h2>
    <span class="badge badge-motor">motor</span>
  </div>
  <p class="desc">Controls a paired left/right drive motor setup. Extends <code>legoeducation.DoubleMotor</code>.</p>
  <table>
    <thead><tr><th>Method</th><th>Parameters</th><th>Description</th></tr></thead>
    <tbody>
      <tr><td><code>connect(card_color, card_serial)</code></td><td><code>card_color</code>, <code>card_serial</code></td><td>Connects with up to 5 retries.</td></tr>
      <tr><td><code>move_steps(step=1)</code></td><td><code>step</code> <em>int/float, default 1</em> — 1 step = 180°</td><td>Moves both motors for the given number of steps.</td></tr>
      <tr><td><code>run()</code></td><td>—</td><td>Runs both motors continuously in the backward direction.</td></tr>
      <tr><td><code>run_time(time=2000)</code></td><td><code>time</code> <em>int, default 2000</em> – milliseconds</td><td>Runs both motors for a fixed duration.</td></tr>
      <tr><td><code>run_left(degrees=None)</code></td><td><code>degrees</code> – <code>None</code> for continuous, or exact degrees</td><td>Runs the left motor counter-clockwise.</td></tr>
      <tr><td><code>run_right(degrees=None)</code></td><td><code>degrees</code> – <code>None</code> for continuous, or exact degrees</td><td>Runs the right motor counter-clockwise.</td></tr>
      <tr><td><code>turn_left(degrees=90)</code></td><td><code>degrees</code> <em>int/float, default 90</em></td><td>Turns the robot left.</td></tr>
      <tr><td><code>turn_right(degrees=90)</code></td><td><code>degrees</code> <em>int/float, default 90</em></td><td>Turns the robot right.</td></tr>
      <tr><td><code>set_speed(speed)</code></td><td><code>speed</code></td><td>Sets speed of both motors simultaneously.</td></tr>
      <tr><td><code>set_speed_left(speed)</code></td><td><code>speed</code></td><td>Sets speed of the left motor only.</td></tr>
      <tr><td><code>set_speed_right(speed)</code></td><td><code>speed</code></td><td>Sets speed of the right motor only.</td></tr>
      <tr><td><code>stop()</code></td><td>—</td><td>Stops both motors.</td></tr>
    </tbody>
  </table>
</div>

<div class="section">
  <div class="section-header">
    <h2>controller</h2>
    <span class="badge badge-controller">input</span>
  </div>
  <p class="desc">Reads input from a LEGO controller (two joysticks). Extends <code>legoeducation.Controller</code>.</p>
  <table>
    <thead><tr><th>Method</th><th>Parameters</th><th>Returns</th><th>Description</th></tr></thead>
    <tbody>
      <tr><td><code>connect(card_color, card_serial)</code></td><td><code>card_color</code>, <code>card_serial</code></td><td>—</td><td>Connects with up to 5 retries.</td></tr>
      <tr><td><code>left_up()</code></td><td>—</td><td><span class="ret">bool</span></td><td><code>True</code> when left joystick is pushed up.</td></tr>
      <tr><td><code>left_down()</code></td><td>—</td><td><span class="ret">bool</span></td><td><code>True</code> when left joystick is pushed down.</td></tr>
      <tr><td><code>left_released()</code></td><td>—</td><td><span class="ret">bool</span></td><td><code>True</code> when left joystick is centered.</td></tr>
      <tr><td><code>right_up()</code></td><td>—</td><td><span class="ret">bool</span></td><td><code>True</code> when right joystick is pushed up.</td></tr>
      <tr><td><code>right_down()</code></td><td>—</td><td><span class="ret">bool</span></td><td><code>True</code> when right joystick is pushed down.</td></tr>
      <tr><td><code>right_released()</code></td><td>—</td><td><span class="ret">bool</span></td><td><code>True</code> when right joystick is centered.</td></tr>
      <tr><td><code>left_position()</code></td><td>—</td><td><span class="ret">int/float</span></td><td>Raw percent of left joystick (negative = down, positive = up).</td></tr>
      <tr><td><code>right_position()</code></td><td>—</td><td><span class="ret">int/float</span></td><td>Raw percent of right joystick.</td></tr>
      <tr><td><code>drive(dm, t=100)</code></td><td><code>dm</code> – a <code>doubleMotor</code> instance<br><code>t</code> <em>int, default 100</em> – ticks (×0.1 s each)</td><td>—</td><td>Tank-drives <code>dm</code> using both joystick positions for <code>t×0.1</code> seconds.</td></tr>
    </tbody>
  </table>
</div>

<div class="section">
  <div class="section-header">
    <h2>colorSensor</h2>
    <span class="badge badge-sensor">sensor</span>
  </div>
  <p class="desc">Reads color data from a LEGO color sensor. Extends <code>legoeducation.ColorSensor</code>.</p>
  <table>
    <thead><tr><th>Method</th><th>Parameters</th><th>Returns</th><th>Description</th></tr></thead>
    <tbody>
      <tr><td><code>connect(card_color, card_serial)</code></td><td><code>card_color</code>, <code>card_serial</code></td><td>—</td><td>Connects with up to 5 retries.</td></tr>
      <tr><td><code>reflection()</code></td><td>—</td><td><span class="ret">int/float</span></td><td>Raw reflection value (0–255).</td></tr>
      <tr><td><code>detect_color()</code></td><td>—</td><td><span class="ret">str</span></td><td>Name of the detected color (see mapping below).</td></tr>
    </tbody>
  </table>

  <p class="color-section-label">Color mapping</p>
  <div class="color-grid">
    <div class="color-swatch"><div class="swatch-color" style="background:#eee"></div><div class="swatch-label">0 – No color</div></div>
    <div class="color-swatch"><div class="swatch-color" style="background:#e63946"></div><div class="swatch-label">1 – Red</div></div>
    <div class="color-swatch"><div class="swatch-color" style="background:#f7b731"></div><div class="swatch-label">2 – Yellow</div></div>
    <div class="color-swatch"><div class="swatch-color" style="background:#3a86ff"></div><div class="swatch-label">3 – Blue</div></div>
    <div class="color-swatch"><div class="swatch-color" style="background:#2ec4b6"></div><div class="swatch-label">4 – Teal</div></div>
    <div class="color-swatch"><div class="swatch-color" style="background:#2d9e48"></div><div class="swatch-label">5 – Green</div></div>
    <div class="color-swatch"><div class="swatch-color" style="background:#8338ec"></div><div class="swatch-label">6 – Purple</div></div>
    <div class="color-swatch"><div class="swatch-color" style="background:#f8f9fa"></div><div class="swatch-label">7 – White</div></div>
    <div class="color-swatch"><div class="swatch-color" style="background:#d63384"></div><div class="swatch-label">8 – Magenta</div></div>
    <div class="color-swatch"><div class="swatch-color" style="background:#fd7c2a"></div><div class="swatch-label">9 – Orange</div></div>
    <div class="color-swatch"><div class="swatch-color" style="background:#4cc9f0"></div><div class="swatch-label">10 – Azure</div></div>
    <div class="color-swatch"><div class="swatch-color" style="background:#adb5bd"></div><div class="swatch-label">other – Unknown</div></div>
  </div>
</div>

</body>
</html>



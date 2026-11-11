package dev.tachyon.bench;

import java.lang.reflect.Method;
import java.util.Locale;
import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.WorldCreator;
import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.event.Event;
import org.bukkit.event.EventHandler;
import org.bukkit.event.HandlerList;
import org.bukkit.event.Listener;
import org.bukkit.plugin.java.JavaPlugin;

/**
 * Mess-Plugin fuer benchmark.py. Laeuft identisch auf Spigot und Tachyon.
 * Gibt Ergebnisse als "[BENCH] RESULT <name> key=value ..." in der Konsole aus.
 *
 * Messprinzip: Ein Task laeuft jeden Tick und misst den Abstand zum vorherigen Tick.
 * Normal sind 50 ms. Friert der Main-Thread ein, wird der Abstand entsprechend groesser.
 */
public final class BenchPlugin extends JavaPlugin {

    private long lastTick;
    private long maxIntervalNanos;
    private long ticks;
    private Method tickTimes;
    private Object nmsServer;

    @Override
    public void onEnable() {
        try {
            Class<?> ms = Class.forName("net.minecraft.server.MinecraftServer");
            nmsServer = ms.getMethod("getServer").invoke(null);
            tickTimes = ms.getMethod("getTickTimesNanos");
        } catch (ReflectiveOperationException e) {
            getLogger().warning("MSPT-Messung nicht verfuegbar: " + e);
        }
        Bukkit.getScheduler().runTaskTimer(this, () -> {
            long now = System.nanoTime();
            if (lastTick != 0) {
                maxIntervalNanos = Math.max(maxIntervalNanos, now - lastTick);
            }
            lastTick = now;
            ticks++;
        }, 1L, 1L);
        getLogger().info("[BENCH] READY server=" + Bukkit.getName());
    }

    private void resetWindow() {
        maxIntervalNanos = 0;
        ticks = 0;
    }

    private double avgMspt() {
        try {
            long[] t = (long[]) tickTimes.invoke(nmsServer);
            long sum = 0;
            int n = 0;
            for (long v : t) {
                if (v > 0) {
                    sum += v;
                    n++;
                }
            }
            return n == 0 ? -1 : sum / (double) n / 1e6;
        } catch (Exception e) {
            return -1;
        }
    }

    private static void result(String name, String data) {
        Bukkit.getLogger().info("[BENCH] RESULT " + name + " " + data);
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (args.length == 0) {
            sender.sendMessage("bench <idle <sek>|createworld <name>|mem>");
            return true;
        }
        switch (args[0].toLowerCase(Locale.ROOT)) {
            case "idle" -> idle(args.length > 1 ? Integer.parseInt(args[1]) : 10);
            case "createworld" -> createWorld(args.length > 1 ? args[1] : "bench_world");
            case "mem" -> mem();
            case "events" -> events(args.length > 1 ? Integer.parseInt(args[1]) : 2_000_000);
            default -> sender.sendMessage("unbekannt");
        }
        return true;
    }

    private void idle(int seconds) {
        resetWindow();
        long start = System.nanoTime();
        Bukkit.getScheduler().runTaskLater(this, () -> {
            double secs = (System.nanoTime() - start) / 1e9;
            result("idle", String.format(Locale.ROOT, "tps=%.2f mspt=%.2f max_tick_ms=%.1f",
                    ticks / secs, avgMspt(), maxIntervalNanos / 1e6));
        }, seconds * 20L);
    }

    private void createWorld(String name) {
        resetWindow();
        long start = System.nanoTime();
        boolean tachyon = isTachyon();
        if (tachyon) {
            Bukkit.dispatchCommand(Bukkit.getConsoleSender(), "wm create " + name);
        } else {
            Bukkit.createWorld(new WorldCreator(name)); // Original: blockiert den Main-Thread bis fertig
        }
        long returned = System.nanoTime();
        int[] taskId = new int[1];
        taskId[0] = Bukkit.getScheduler().scheduleSyncRepeatingTask(this, () -> {
            World w = Bukkit.getWorld(name);
            if (w == null || !isReady(w)) {
                if ((System.nanoTime() - start) > 300_000_000_000L) {
                    result("createworld", "error=timeout");
                    Bukkit.getScheduler().cancelTask(taskId[0]);
                }
                return;
            }
            Bukkit.getScheduler().cancelTask(taskId[0]);
            long ready = System.nanoTime();
            // Noch 3 s weiter messen, um Nachlaeufer-Lags mitzunehmen
            Bukkit.getScheduler().runTaskLater(this, () -> {
                double secs = (System.nanoTime() - start) / 1e9;
                result("createworld", String.format(Locale.ROOT,
                        "freeze_ms=%.1f blocked_call_ms=%.1f ready_ms=%.1f tps=%.2f",
                        maxIntervalNanos / 1e6, (returned - start) / 1e6, (ready - start) / 1e6, ticks / secs));
            }, 60L);
        }, 1L, 1L);
    }

    private static boolean isTachyon() {
        try {
            Class.forName("dev.tachyon.world.WorldManager");
            return true;
        } catch (ClassNotFoundException e) {
            return false;
        }
    }

    /** Tachyon: World-Manager meldet "bereit". Original: Welt existiert = fertig (createWorld blockiert bis dahin). */
    private boolean isReady(World w) {
        try {
            Class<?> wmClass = Class.forName("dev.tachyon.world.WorldManager");
            Object wm = wmClass.getMethod("get").invoke(null);
            return (boolean) wmClass.getMethod("isReady", World.class).invoke(wm, w);
        } catch (ClassNotFoundException e) {
            return true;
        } catch (ReflectiveOperationException e) {
            return true;
        }
    }

    /** Eigenes Test-Event mit 5 Listenern: misst, wie schnell das Event-System Listener aufruft. */
    public static final class BenchEvent extends Event {
        private static final HandlerList HANDLERS = new HandlerList();
        int counter;

        @Override
        public HandlerList getHandlers() {
            return HANDLERS;
        }

        public static HandlerList getHandlerList() {
            return HANDLERS;
        }
    }

    public static final class BenchListener implements Listener {
        @EventHandler public void a(BenchEvent e) { e.counter++; }
        @EventHandler public void b(BenchEvent e) { e.counter++; }
        @EventHandler public void c(BenchEvent e) { e.counter++; }
        @EventHandler public void d(BenchEvent e) { e.counter++; }
        @EventHandler public void f(BenchEvent e) { e.counter++; }
    }

    private boolean listenerRegistered;

    private void events(int n) {
        if (!listenerRegistered) {
            Bukkit.getPluginManager().registerEvents(new BenchListener(), this);
            listenerRegistered = true;
        }
        BenchEvent ev = new BenchEvent();
        for (int i = 0; i < 200_000; i++) { // Aufwaermen fuer den JIT
            Bukkit.getPluginManager().callEvent(ev);
        }
        long start = System.nanoTime();
        for (int i = 0; i < n; i++) {
            Bukkit.getPluginManager().callEvent(ev);
        }
        long nanos = System.nanoTime() - start;
        result("events", String.format(Locale.ROOT, "ns_per_event=%.1f calls=%d", nanos / (double) n, ev.counter));
    }

    private void mem() {
        Runtime rt = Runtime.getRuntime();
        System.gc();
        long used = rt.totalMemory() - rt.freeMemory();
        result("mem", String.format(Locale.ROOT, "heap_used_mb=%.1f heap_committed_mb=%.1f",
                used / 1048576.0, rt.totalMemory() / 1048576.0));
    }
}

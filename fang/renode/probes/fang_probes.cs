// Probes fang adds to an emulated platform, so that what a device was asked,
// what a pin did, and what a UART carried are recorded by the emulator itself
// rather than taken from the firmware's account of itself.
//
// Every event goes to one file, one JSON object per line:
//   {"seq": n, "t_ns": virtual nanoseconds, "source": "<entity id>",
//    "type": "...", "payload": {...}}
// The source is the identifier of the fang entity the probe stands for, so the
// record is in the board's terms and not the emulator's. Logging is switched
// to synchronous so that events taken from the log interleave with the
// probes' own in one deterministic order.
//
// Loaded by the script with `include @fang_probes.cs`; compiled by Renode at
// load time. Written for Renode 1.17.0.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using Antmicro.Renode.Core;
using Antmicro.Renode.Logging;
using Antmicro.Renode.Peripherals.Bus;
using Antmicro.Renode.Peripherals.I2C;
using Antmicro.Renode.Peripherals.UART;

namespace Antmicro.Renode.Peripherals.Fang
{
    // The one writer of the event file. Registered on a GPIO port as a
    // container child, like an LED, and never connected, so it is addressable
    // from the script and invisible to the firmware.
    public class EventRecorder : IGPIOReceiver
    {
        public EventRecorder(IMachine machine)
        {
            this.machine = machine;

            var logger = EmulationManager.Instance.CurrentEmulation.CurrentLogger;
            logger.SynchronousLogging = true;
            backend = new WarningBackend(this);
            Logger.AddBackend(backend, "fang-events", true);
        }

        // Opens the event file. The script passes the path with Renode's @
        // syntax, so it is resolved against the bundle rather than against
        // the directory Renode's launcher runs from. Events recorded before
        // this are kept and written first.
        public void Open(string path)
        {
            lock(sync)
            {
                writer = new StreamWriter(path, false, new UTF8Encoding(false));
                writer.NewLine = "\n";
                foreach(var line in pending)
                {
                    writer.Write(line);
                }
                pending.Clear();
                writer.Flush();
            }
            Write(null, "", "run.start", "{}");
        }

        // Records every write the firmware makes to one 32-bit register. Used
        // for configuration registers a model accepts without storing, such
        // as the STM32 GPIO output-type register, whose value cannot be read
        // back.
        public void WatchWrites(string source, string peripheral, string register, ulong address)
        {
            machine.SystemBus.AddWatchpointHook(address, SysbusAccessWidth.DoubleWord, Access.Write,
                (cpu, hookAddress, width, value) => Record(source, "register.write", string.Format(CultureInfo.InvariantCulture,
                    "{{\"address\":\"0x{0:X8}\",\"peripheral\":{1},\"register\":{2},\"value\":\"0x{3:X8}\"}}",
                    hookAddress, Json(peripheral), Json(register), value)));
        }

        public void OnGPIO(int number, bool value)
        {
        }

        public void Reset()
        {
        }

        // Records an event at the current virtual time, synchronizing the
        // calling CPU first so the stamp is the instruction's and not the
        // quantum's.
        public void Record(string source, string type, string payload)
        {
            if(machine.SystemBus.TryGetCurrentCPU(out var cpu))
            {
                cpu.SyncTime();
            }
            Write(null, source, type, payload);
        }

        // Reads one 32-bit register through the system bus and records it.
        // Called by the script between run segments, and only for registers
        // without read side effects.
        public void Snapshot(string source, string peripheral, string register, ulong address)
        {
            var value = machine.SystemBus.ReadDoubleWord(address);
            Write(null, source, "register.snapshot", string.Format(CultureInfo.InvariantCulture,
                "{{\"address\":\"0x{0:X8}\",\"peripheral\":{1},\"register\":{2},\"value\":\"0x{3:X8}\"}}",
                address, Json(peripheral), Json(register), value));
        }

        public void Finish(string reason)
        {
            Write(null, "", "run.end", "{\"reason\":" + Json(reason) + "}");
            lock(sync)
            {
                writer?.Flush();
                writer?.Dispose();
                closed = true;
            }
        }

        public void Watch(object target, string source)
        {
            var id = EmulationManager.Instance.CurrentEmulation.CurrentLogger.GetOrCreateSourceId(target);
            lock(sync)
            {
                watched[id] = source;
            }
        }

        internal void OnLogEntry(LogEntry entry)
        {
            string source;
            lock(sync)
            {
                if(!watched.TryGetValue(entry.SourceId, out source))
                {
                    return;
                }
            }
            var nack = NackPattern.Match(entry.Message ?? "");
            if(nack.Success)
            {
                var address = Convert.ToInt32(nack.Groups[1].Value, 16);
                Record(source, "i2c.nack",
                    string.Format(CultureInfo.InvariantCulture, "{{\"address\":{0}}}", address));
                return;
            }
            Record(source, "model.warning", "{\"text\":" + Json(entry.Message) + "}");
        }

        public static string Json(string text)
        {
            var builder = new StringBuilder("\"");
            foreach(var c in text ?? "")
            {
                switch(c)
                {
                case '"': builder.Append("\\\""); break;
                case '\\': builder.Append("\\\\"); break;
                case '\n': builder.Append("\\n"); break;
                case '\r': builder.Append("\\r"); break;
                case '\t': builder.Append("\\t"); break;
                default:
                    if(c < 0x20)
                    {
                        builder.AppendFormat(CultureInfo.InvariantCulture, "\\u{0:x4}", (int)c);
                    }
                    else
                    {
                        builder.Append(c);
                    }
                    break;
                }
            }
            return builder.Append('"').ToString();
        }

        public static string Bytes(IEnumerable<byte> data)
        {
            return "[" + string.Join(",", data.Select(b => b.ToString(CultureInfo.InvariantCulture))) + "]";
        }

        private void Write(ulong? timeNs, string source, string type, string payload)
        {
            lock(sync)
            {
                if(closed)
                {
                    return;
                }
                var t = timeNs ?? machine.ElapsedVirtualTime.TimeElapsed.TotalNanoseconds;
                var line = string.Format(CultureInfo.InvariantCulture,
                    "{{\"seq\":{0},\"t_ns\":{1},\"source\":{2},\"type\":{3},\"payload\":{4}}}\n",
                    sequence++, t, Json(source), Json(type), payload);
                if(writer == null)
                {
                    pending.Add(line);
                    return;
                }
                writer.Write(line);
                writer.Flush();
            }
        }

        private readonly IMachine machine;
        private StreamWriter writer;
        private readonly List<string> pending = new List<string>();
        private readonly WarningBackend backend;
        private readonly Dictionary<int, string> watched = new Dictionary<int, string>();
        private readonly object sync = new object();
        private ulong sequence;
        private bool closed;

        private static readonly Regex NackPattern =
            new Regex("Child address changed to 0x([0-9A-Fa-f]+), but target is not registered");

        private class WarningBackend : LoggerBackend
        {
            public WarningBackend(EventRecorder recorder)
            {
                this.recorder = recorder;
            }

            public override void Log(LogEntry entry, Logger.TimestampType timestampType)
            {
                if(entry.Type >= LogLevel.Warning)
                {
                    recorder.OnLogEntry(entry);
                }
            }

            private readonly EventRecorder recorder;
        }
    }

    // An I2C target that stands in front of a real model: it registers at the
    // device's address, forwards every call to the model, and records each.
    public class I2CProbe : II2CPeripheral
    {
        public I2CProbe(IMachine machine, EventRecorder recorder, string model, string source)
        {
            this.recorder = recorder;
            this.source = source;
            inner = Instantiate(model, machine);
            recorder.Watch(inner, source);
        }

        public void Write(byte[] data)
        {
            recorder.Record(source, "i2c.write", "{\"data\":" + EventRecorder.Bytes(data) + "}");
            inner.Write(data);
        }

        public byte[] Read(int count = 1)
        {
            var data = inner.Read(count);
            recorder.Record(source, "i2c.read", "{\"data\":" + EventRecorder.Bytes(data) + "}");
            return data;
        }

        public void FinishTransmission()
        {
            recorder.Record(source, "i2c.stop", "{}");
            inner.FinishTransmission();
        }

        public void Reset()
        {
            inner.Reset();
        }

        // A stimulus: sets one of the model's inputs, given as a decimal
        // string so that the value crosses into the emulator exactly.
        public void SetInput(string input, string value)
        {
            var property = inner.GetType().GetProperty(input, BindingFlags.Public | BindingFlags.Instance);
            if(property == null || !property.CanWrite)
            {
                throw new ArgumentException($"{inner.GetType().Name} has no settable input {input}");
            }
            var parsed = decimal.Parse(value, NumberStyles.Float, CultureInfo.InvariantCulture);
            recorder.Record(source, "stimulus",
                "{\"input\":" + EventRecorder.Json(input) + ",\"value\":" + EventRecorder.Json(value) + "}");
            property.SetValue(inner, Convert.ChangeType(parsed, property.PropertyType, CultureInfo.InvariantCulture));
        }

        private static II2CPeripheral Instantiate(string typeName, IMachine machine)
        {
            var type = AppDomain.CurrentDomain.GetAssemblies()
                .Select(assembly => assembly.GetType(typeName, false))
                .FirstOrDefault(t => t != null);
            if(type == null || !typeof(II2CPeripheral).IsAssignableFrom(type))
            {
                throw new ArgumentException($"no I2C model {typeName}");
            }
            foreach(var constructor in type.GetConstructors())
            {
                var parameters = constructor.GetParameters();
                if(parameters.Length == 0 || !typeof(IMachine).IsAssignableFrom(parameters[0].ParameterType))
                {
                    continue;
                }
                if(parameters.Skip(1).Any(p => !p.HasDefaultValue))
                {
                    continue;
                }
                var arguments = new object[parameters.Length];
                arguments[0] = machine;
                for(var i = 1; i < parameters.Length; i++)
                {
                    arguments[i] = parameters[i].DefaultValue;
                }
                return (II2CPeripheral)constructor.Invoke(arguments);
            }
            throw new ArgumentException($"{typeName} has no constructor taking only a machine");
        }

        private readonly EventRecorder recorder;
        private readonly II2CPeripheral inner;
        private readonly string source;
    }

    // A receiver on one pin's output, recording each edge.
    public class GpioProbe : IGPIOReceiver
    {
        public GpioProbe(EventRecorder recorder, string source)
        {
            this.recorder = recorder;
            this.source = source;
        }

        public void OnGPIO(int number, bool value)
        {
            if(value == level)
            {
                return;
            }
            level = value;
            recorder.Record(source, "gpio.edge", value ? "{\"level\":1}" : "{\"level\":0}");
        }

        public void Reset()
        {
            level = false;
        }

        private readonly EventRecorder recorder;
        private readonly string source;
        private bool level;
    }

    // A listener on a UART's transmitter, recording each line the firmware
    // sends, without its line ending.
    public class UartProbe : IGPIOReceiver
    {
        public UartProbe(EventRecorder recorder, IUART uart, string source)
        {
            this.recorder = recorder;
            this.source = source;
            uart.CharReceived += OnCharacter;
        }

        public void OnGPIO(int number, bool value)
        {
        }

        public void Reset()
        {
            line.Clear();
        }

        private void OnCharacter(byte value)
        {
            if(value == (byte)'\n')
            {
                var text = line.ToString().TrimEnd('\r');
                line.Clear();
                recorder.Record(source, "uart.line", "{\"text\":" + EventRecorder.Json(text) + "}");
                return;
            }
            line.Append((char)value);
        }

        private readonly EventRecorder recorder;
        private readonly string source;
        private readonly StringBuilder line = new StringBuilder();
    }

    // Puts a peripheral's warnings into the event record under an entity: the
    // I2C controller's address NACK, or a model's report of something it does
    // not implement. Logging is synchronous, so a warning arrives on the CPU
    // thread that caused it and is stamped like a probe's event. Renode's
    // logger collapses a run of identical messages into one entry, so a
    // repeated warning is recorded once.
    public class WarningProbe : IGPIOReceiver
    {
        public WarningProbe(EventRecorder recorder, IPeripheral target, string source)
        {
            recorder.Watch(target, source);
        }

        public void OnGPIO(int number, bool value)
        {
        }

        public void Reset()
        {
        }
    }
}

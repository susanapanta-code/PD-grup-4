using MQTTnet;
using MQTTnet.Client;
using MQTTnet.Client.Options;
using Newtonsoft.Json;
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace Formulario
{
    public partial class Form1 : Form
    {
        IMqttClient client;

        Dictionary<string, object> ultimaTelemetria = null;
        bool telemetriaActiva = false;

        public Form1()
        {
            InitializeComponent();
            CheckForIllegalCrossThreadCalls = false;

            ConfigurarBotones();
            ConectarMQTT();
        }

        // ================= MQTT =================

        private async void ConectarMQTT()
        {
            var factory = new MqttFactory();
            client = factory.CreateMqttClient();

            var options = new MqttClientOptionsBuilder()
                .WithWebSocketServer("broker.hivemq.com:8000/mqtt")
                .Build();

            client.UseApplicationMessageReceivedHandler(e =>
            {
                string topic = e.ApplicationMessage.Topic;

                string payload = "";
                if (e.ApplicationMessage.Payload != null)
                {
                    payload = Encoding.UTF8.GetString(e.ApplicationMessage.Payload);
                }

                ProcesarMensaje(topic, payload);
            });

            await client.ConnectAsync(options);
            await client.SubscribeAsync("autopilotServiceDemo/interfazGlobal/#");
        }

        private void ProcesarMensaje(string topic, string payload)
        {
            // ---- EVENTOS ----

            if (topic.EndsWith("/connected"))
            {
                but_connect.BackColor = Color.Green;
                but_connect.ForeColor = Color.White;
                but_connect.Text = "Conectado";
            }

            else if (topic.EndsWith("/flying"))
            {
                SetEstado("flying");
            }

            else if (topic.EndsWith("/landed"))
            {
                SetEstado("landed");
            }

            else if (topic.EndsWith("/atHome"))
            {
                SetEstado("atHome");
            }

            // ---- TELEMETRÍA ----

            else if (topic.EndsWith("/telemetryInfo"))
            {
                var data = JsonConvert.DeserializeObject<Dictionary<string, object>>(payload);

                // 🔹 Guardar SIEMPRE
                ultimaTelemetria = data;

                // 🔹 Mostrar SOLO si está activa
                if (telemetriaActiva)
                {
                    MostrarTelemetria(data);
                }
            }
        }

        private void MostrarTelemetria(Dictionary<string, object> data)
        {
            latitudLbl.Text = data.ContainsKey("lat") && data["lat"] != null
                ? data["lat"].ToString()
                : "";

            longitudLbl.Text = data.ContainsKey("lon") && data["lon"] != null
                ? data["lon"].ToString()
                : "";

            altitudLbl.Text = data.ContainsKey("alt") ? data["alt"].ToString() : "";

            headLbl.Text = data.ContainsKey("heading") ? data["heading"].ToString() : "";

            flightModeLbl.Text =
                data.ContainsKey("flightMode") && data["flightMode"] != null
                ? data["flightMode"].ToString()
                : "";

            if (data.ContainsKey("lat") && data["lat"] != null && data.ContainsKey("lon") && data["lon"] != null)
            {
                string lat = Convert.ToDouble(data["lat"]).ToString(CultureInfo.InvariantCulture);
                string lon = Convert.ToDouble(data["lon"]).ToString(CultureInfo.InvariantCulture);

                webView21.ExecuteScriptAsync($"actualizarPos({lat}, {lon});");
            }
        }

        // ================= ESTADO UI =================

        private void ResetBotones()
        {
            Color baseColor = Color.FromArgb(255, 192, 128);

            despegarBtn.BackColor = baseColor;
            despegarBtn.ForeColor = Color.Black;
            despegarBtn.Text = "Despegar";

            button7.BackColor = baseColor;
            button7.ForeColor = Color.Black;
            button7.Text = "Aterrizar";

            button6.BackColor = baseColor;
            button6.ForeColor = Color.Black;
            button6.Text = "RTL";
        }

        private void SetEstado(string estado)
        {
            ResetBotones();

            if (estado == "flying")
            {
                despegarBtn.BackColor = Color.Green;
                despegarBtn.ForeColor = Color.White;
                despegarBtn.Text = "En el aire";
            }
            else if (estado == "landed")
            {
                button7.BackColor = Color.Green;
                button7.ForeColor = Color.White;
                button7.Text = "En tierra";
            }
            else if (estado == "atHome")
            {
                button6.BackColor = Color.Green;
                button6.ForeColor = Color.White;
                button6.Text = "En tierra";
            }
        }

        // ================= CONFIG BOTONES =================

        private void ConfigurarBotones()
        {
            Font grande = new Font("Arial", 14);

            button9.Tag = "NorthWest";
            button10.Tag = "North";
            button11.Tag = "NorthEast";
            button12.Tag = "West";
            button13.Tag = "Stp";
            button14.Tag = "East";
            button15.Tag = "SouthWest";
            button16.Tag = "South";
            button17.Tag = "SouthEast";

            foreach (Button b in new[] {
                button9, button10, button11,
                button12, button13, button14,
                button15, button16, button17 })
            {
                b.Click += navButton_Click;
                b.Font = grande;
            }
        }

        // ================= BOTONES =================

        private async void but_connect_Click(object sender, EventArgs e)
        {
            await client.PublishAsync("interfazGlobal/autopilotServiceDemo/connect");
        }

        private async void but_takeoff_Click(object sender, EventArgs e)
        {
            ResetBotones();

            despegarBtn.BackColor = Color.Yellow;
            despegarBtn.Text = "Despegando...";

            await client.PublishAsync("interfazGlobal/autopilotServiceDemo/arm_takeOff");
        }

        private async void aterrizarBtn_Click(object sender, EventArgs e)
        {
            ResetBotones();

            button7.BackColor = Color.Yellow;
            button7.Text = "Aterrizando...";

            await client.PublishAsync("interfazGlobal/autopilotServiceDemo/Land");
        }

        private async void RTLBtn_Click(object sender, EventArgs e)
        {
            ResetBotones();

            button6.BackColor = Color.Yellow;
            button6.Text = "Retornando...";

            await client.PublishAsync("interfazGlobal/autopilotServiceDemo/RTL");
        }

        private async void navButton_Click(object sender, EventArgs e)
        {
            Button b = (Button)sender;
            string direccion = b.Tag.ToString();

            await client.PublishAsync(
                "interfazGlobal/autopilotServiceDemo/go",
                Encoding.UTF8.GetBytes(direccion)
            );
        }

        private async void enviarTelemetriaBtn_Click(object sender, EventArgs e)
        {
            telemetriaActiva = true;

            // Mostrar inmediatamente lo último recibido
            if (ultimaTelemetria != null)
            {
                MostrarTelemetria(ultimaTelemetria);
            }

            await client.PublishAsync("interfazGlobal/autopilotServiceDemo/startTelemetry");
        }

        private async void detenerTelemetriaBtn_Click(object sender, EventArgs e)
        {
            telemetriaActiva = false;

            await client.PublishAsync("interfazGlobal/autopilotServiceDemo/stopTelemetry");
        }

        private void headingTrackBar_Scroll(object sender, EventArgs e)
        {
            headingLbl.Text = headingTrackBar.Value.ToString();
        }

        private async void headingTrackBar_MouseUp(object sender, MouseEventArgs e)
        {
            int valor = headingTrackBar.Value;

            await client.PublishAsync(
                "interfazGlobal/autopilotServiceDemo/changeHeading",
                Encoding.UTF8.GetBytes(valor.ToString())
            );
        }

        private void velocidadTrackBar_Scroll(object sender, EventArgs e)
        {
            velocidadLbl.Text = velocidadTrackBar.Value.ToString();
        }

        private async void velocidadTrackBar_MouseUp(object sender, MouseEventArgs e)
        {
            int valor = velocidadTrackBar.Value;

            await client.PublishAsync(
                "interfazGlobal/autopilotServiceDemo/changeNavSpeed",
                Encoding.UTF8.GetBytes(valor.ToString())
            );
        }

        private void metrosDespegue_trackBar_Scroll(object sender, EventArgs e)
        {
            alturaBox.Text = metrosDespegue_trackBar.Value.ToString();
        }

        private async void ArmarBtn_Click_Click(object sender, EventArgs e)
        {
            await client.PublishAsync("interfazGlobal/autopilotServiceDemo/arm_takeOff");
        }

        private async void CoreWebView2_WebMessageReceived(object sender, Microsoft.Web.WebView2.Core.CoreWebView2WebMessageReceivedEventArgs e)
        {
            var json = e.WebMessageAsJson;

            dynamic data = Newtonsoft.Json.JsonConvert.DeserializeObject(json);

            double lat = (double)data.lat;
            double lon = (double)data.lon;

            string latStr = lat.ToString(CultureInfo.InvariantCulture);
            string lonStr = lon.ToString(CultureInfo.InvariantCulture);

            await client.PublishAsync(
                "interfazGlobal/autopilotServiceDemo/goTo",
                Encoding.UTF8.GetBytes($"{latStr},{lonStr}")
            );
        }

        private async void limpiarMapaBtn_Click(object sender, EventArgs e)
        {
            await webView21.ExecuteScriptAsync("limpiarRuta();");
        }

        private async void Form1_Load(object sender, EventArgs e)
        {
            await webView21.EnsureCoreWebView2Async(null);
            webView21.CoreWebView2.WebMessageReceived += CoreWebView2_WebMessageReceived;
            webView21.CoreWebView2.Settings.IsScriptEnabled = true;
            webView21.CoreWebView2.Settings.AreHostObjectsAllowed = true;

            webView21.CoreWebView2.Settings.IsWebMessageEnabled = true;
            webView21.CoreWebView2.Settings.AreDefaultScriptDialogsEnabled = true;
            webView21.CoreWebView2.Settings.IsStatusBarEnabled = true;

            webView21.Source = new Uri(Application.StartupPath + "\\map.html");
        }
    }
}

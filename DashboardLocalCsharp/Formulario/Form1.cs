using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Diagnostics;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
using csDronLink;

namespace Formulario
{
    public partial class Form1 : Form
    {
        Dron dron = new Dron();

        public Form1()
        {
            InitializeComponent();
            // No queremos que nos molesten con la excepción Cross-Threading
            CheckForIllegalCrossThreadCalls = false;
            // Configuramos los 9 botones de movimiento. Todos ellos tendrán asociada la misma función
            // para gestionar el evento click, pero en el tag ponemos la palabra que identifica la dirección 
            // del movimiento, que es la palabra que hay que pasarle como parámetro al dron para que haga la
            // operación. El texto es el código de una flechita que representa la dirección del movimineto.

            Font letraGrande = new Font("Arial", 14);
            Font letraPequeña = new Font("Arial", 12);

            // Ahora configuramos los botones de navegación

            button9.Text = "NW";
            button9.Tag = "NorthWest";
            button9.Click += navButton_Click;
            button9.Font = letraGrande;


            button10.Text = "N";
            button10.Tag = "North";
            button10.Click += navButton_Click;
            button10.Font = letraGrande;


            button11.Text = "NE";
            button11.Tag = "NorthEast";
            button11.Click += navButton_Click;
            button11.Font = letraGrande;


            button12.Text = "W";
            button12.Tag = "West";
            button12.Click += navButton_Click;
            button12.Font = letraGrande;


            button13.Text = "Stop";
            button13.Tag = "Stop";
            button13.Click += navButton_Click;
            button13.Font = letraPequeña;


            button14.Text = "E";
            button14.Tag = "East";
            button14.Click += navButton_Click;
            button14.Font = letraGrande;


            button15.Text = "SW";
            button15.Tag = "SouthWest";
            button15.Click += navButton_Click;
            button15.Font = letraGrande;


            button16.Text = "S";
            button16.Tag = "South";
            button16.Click += navButton_Click;
            button16.Font = letraGrande;


            button17.Text = "SE";
            button17.Tag = "SouthEast";
            button17.Click += navButton_Click;
            button17.Font = letraGrande;

        }

        private void but_connect_Click(object sender, EventArgs e)
        {
            //dron.Conectar("simulacion");
            dron.Conectar("produccion","com4");
            but_connect.BackColor = Color.Green;
            but_connect.ForeColor = Color.White;
        }


        private void EnAire(byte id, object param)
        {
            // Esto es lo que haré cuando el dron haya alcanzado la altura de despegue
            despegarBtn.BackColor = Color.Green;
            despegarBtn.ForeColor = Color.White;
            despegarBtn.Text = (string)param;
        }

        private void but_takeoff_Click(object sender, EventArgs e)
        {
            // Restablecer el botón de aterrizar a su estado original
            button7.BackColor = Color.FromArgb(255, 192, 128);
            button7.ForeColor = Color.Black;
            button7.Text = "Aterrizar";

            // Restablecer el botón de RTL a su estado original
            button6.BackColor = Color.FromArgb(255, 192, 128);
            button6.ForeColor = Color.Black;
            button6.Text = "RTL";

            // Click en boton para dspegar
            // Llamada no bloqueante para no bloquear el formulario
            dron.Despegar(metrosDespegue_trackBar.Value, bloquear: false, EnAire, "Volando");
            despegarBtn.BackColor = Color.Yellow;
        }

        private void navButton_Click(object sender, EventArgs e)
        {
            // Aqui vendremos cuando se clique cualquiera de los botones de navagación
            // En el tag del boton tenemos la dirección de navegación.
            Button b = (Button)sender;
            string tag = b.Tag.ToString();
            dron.Navegar(tag);

        }

        private void EnTierra(byte id, object mensaje)
        {
            // Aqui vendre cuando el dron esté en tierra
            // El mensaje me dice si vengo de un aterrizaje o de un RTL

            // Restablecer el botón de despegue a su estado original
            despegarBtn.BackColor = Color.FromArgb(255, 192, 128);
            despegarBtn.ForeColor = Color.Black;
            despegarBtn.Text = "Despegar"; 

            if ((string)mensaje == "Aterrizaje")
                button7.BackColor = Color.Green;
            else
                button6.BackColor = Color.Green;
        }



        private void aterrizarBtn_Click(object sender, EventArgs e)
        {
            // Click en el botón de aterrizar
            dron.Aterrizar(bloquear: false, EnTierra, "Aterrizaje");
            button7.BackColor = Color.Yellow;
        }

        private void RTLBtn_Click(object sender, EventArgs e)
        {
            // Click en el botón de RTL
            dron.RTL(bloquear: false, EnTierra, "RTL");
            button6.BackColor = Color.Yellow;
        }

        private void enviarTelemetriaBtn_Click(object sender, EventArgs e)
        {

            dron.EnviarDatosTelemetria(ProcesarTelemetria);
        }

        private void detenerTelemetriaBtn_Click(object sender, EventArgs e)
        {
            dron.DetenerDatosTelemetria();
        }

        private void ProcesarTelemetria(byte id, List<(string nombre, float valor)> telemetria)
        {
            // Aqui vendre cada vez que llegue un paquete de telemetría
            double lat = ((double)telemetria[1].valor) / 0.1E+8;
            double lon = ((double)telemetria[2].valor) / 0.1E+8;
            double heading = ((double)telemetria[3].valor) / 100;
            double mode = (double)telemetria[4].valor;
            string modeStr = "";

            //0:    "STABILIZE";
            //3:    "AUTO";
            //4:    "GUIDED";
            //5:    "LOITER";
            //6:    "RTL";
            //9:    "LAND";

             if (mode == 0) {
                modeStr = "STABILIZE"; 
                } else if (mode == 3)
                { modeStr = "AUTO";
                } else if (mode == 4)
                { modeStr = "GUIDED";
                } else if (mode == 5)
                { modeStr = "LOITER";
                } else if (mode == 6)
                { modeStr = "RTL";
                } else if (mode == 9)
                { modeStr = "LAND";
                } 


            // Coloco los datos de telemetria en su sitio
            altitudLbl.Text = telemetria[0].valor.ToString();
            latitudLbl.Text = lat.ToString();
            longitudLbl.Text = lon.ToString();
            headLbl.Text = heading.ToString();
            flightModeLbl.Text = modeStr;

        }

        private void headingTrackBar_Scroll(object sender, EventArgs e)
        {
            // Recojo el valor del heading seleccionado
            int n = headingTrackBar.Value;
            headingLbl.Text = n.ToString();
        }


        private void headingTrackBar_MouseUp(object sender, MouseEventArgs e)
        {
            // Cuando se libera la barra de desplazamiento recojo el valor
            // definitivo para el heading y lo envío al dron
            float valorSeleccionado = headingTrackBar.Value;
            dron.CambiarHeading(valorSeleccionado, bloquear: false);
        }

        private void velocidadTrackBar_Scroll(object sender, EventArgs e)
        {
            // Recojo y muestro el valor la velocidad según se mueve 
            // la barra de desplazamiento
            int n = velocidadTrackBar.Value;
            velocidadLbl.Text = n.ToString();

        }

        private void velocidadTrackBar_MouseUp(object sender, MouseEventArgs e)
        {
            // Cuando se libera la barra de desplazamiento recojo el valor
            // definitivo para la velocidad y lo envío al dron
            int valorSeleccionado = velocidadTrackBar.Value;
            dron.CambiaVelocidad(valorSeleccionado);
        }


        private void metrosDespegue_trackBar_Scroll(object sender, EventArgs e)
        {
            // Actualizar el label con el valor seleccionado
            alturaBox.Text = metrosDespegue_trackBar.Value.ToString();
        }

        private void Form1_Load(object sender, EventArgs e)
        {

        }

        private void ArmarBtn_Click_Click(object sender, EventArgs e)
        {
            dron.PonModoGuiado();
        }
    }
}

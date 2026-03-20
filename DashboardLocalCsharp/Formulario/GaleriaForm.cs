using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

namespace Formulario
{
    public partial class GaleriaForm : Form
    {
        public GaleriaForm()
        {
            InitializeComponent();
            CargarImagenes();
        }

        private void CargarImagenes()
        {
            string carpeta = Path.Combine(Application.StartupPath, "fotos");

            if (!Directory.Exists(carpeta))
                return;

            string[] archivos = Directory.GetFiles(carpeta, "*.jpg");

            foreach (var archivo in archivos)
            {
                PictureBox pb = new PictureBox();
                pb.Width = 150;
                pb.Height = 120;
                pb.SizeMode = PictureBoxSizeMode.Zoom;
                pb.Image = Image.FromFile(archivo);

                pb.Click += (s, e) =>
                {
                    Form f = new Form();
                    PictureBox img = new PictureBox();
                    img.Dock = DockStyle.Fill;
                    img.SizeMode = PictureBoxSizeMode.Zoom;
                    img.Image = Image.FromFile(archivo);
                    f.Controls.Add(img);
                    f.WindowState = FormWindowState.Maximized;
                    f.Show();
                };

                flowLayoutPanel1.Controls.Add(pb);
            }
        }
    }
}
document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("mobileToggle");
  if (toggle) toggle.addEventListener("click", () => document.getElementById("sidebar").classList.toggle("open"));

  const canvas = document.getElementById("financeChart");
  if (canvas && window.Chart) {
    const values = window.fixflowMonthly || [];
    const labels = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    new Chart(canvas, {
      type: "line",
      data: {
        labels,
        datasets: [
          {label:"Income",data:values.map(x=>x.income),borderColor:"#7188ff",backgroundColor:"rgba(113,136,255,.10)",fill:true,tension:.35,borderWidth:2,pointRadius:2},
          {label:"Expenses",data:values.map(x=>x.expense),borderColor:"#37c99a",backgroundColor:"rgba(55,201,154,.06)",fill:true,tension:.35,borderWidth:2,pointRadius:2}
        ]
      },
      options: {
        responsive:true,maintainAspectRatio:false,
        plugins:{legend:{display:false},tooltip:{backgroundColor:"#202b43",padding:10}},
        scales:{
          x:{grid:{display:false},ticks:{color:"#8492aa",font:{size:9}},border:{display:false}},
          y:{beginAtZero:true,grid:{color:"#26334a"},ticks:{color:"#8492aa",font:{size:9},callback:v=>"₹"+Number(v).toLocaleString("en-IN")},border:{display:false}}
        }
      }
    });
  }
});

import { Noto_Sans_Bengali } from "next/font/google";
import "./globals.css";
import Providers from "@/components/Providers";
import Header from "@/components/Header";
import Footer from "@/components/Footer";

const font = Noto_Sans_Bengali({ subsets: ["bengali", "latin"], display: "swap" });

export const metadata = {
  title: "ভূমিপত্র | ডিজিটাল ভূমি রেকর্ড, যাচাই ও ই-মিউটেশন",
  description: "LandTech Innovation Hackathon 2026 প্রোটোটাইপ",
};

export const viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }) {
  return (
    <html lang="bn" className={font.className}>
      <body>
        <Providers>
          <Header />
          <main>
            <div className="wrap">{children}</div>
          </main>
          <Footer />
        </Providers>
      </body>
    </html>
  );
}
